from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from yutto.auth import resolve_auth_file, validate_user_info
from yutto.cli.auth import run_auth
from yutto.cli.compat import normalize_argv
from yutto.cli.credentials import resolve_credential_options
from yutto.cli.event_renderer import CliApplicationEventRenderer
from yutto.cli.formats import run_preview_formats
from yutto.cli.input import config_values_from_cli, expand_download_configs
from yutto.cli.parser import build_parser
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.settings import resolve_config, resolved_config_from_settings, search_for_settings_file
from yutto.config import ResolvedConfig
from yutto.core.application import YuttoApplication
from yutto.core.execution import ExecutionScopeFactory, RequestExecutionScopeFactory
from yutto.core.operation import bind_download_report_sink
from yutto.download_manager import DownloadManager
from yutto.exceptions import ErrorCode, YuttoBaseException
from yutto.utils.console.logger import Badge, Logger
from yutto.utils.ffmpeg import FFmpeg
from yutto.utils.functional import as_sync
from yutto.validator import configure_cli, resolve_credentials, validate_download_config

if TYPE_CHECKING:
    from pathlib import Path

    from yutto.auth import AuthInfo
    from yutto.core.execution import ExecutionScope


def main() -> None:
    parser = build_parser()
    renderer = CliApplicationEventRenderer()
    args = parser.parse_args(normalize_argv(sys.argv[1:]))

    try:
        config = resolve_config(getattr(args, "config", None), search=search_for_settings_file)
    except (OSError, ValueError) as error:
        Logger.error(str(error))
        sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)

    configured = resolved_config_from_settings(config)
    raw_values = vars(args)
    command = raw_values["command"]
    auth_command = raw_values.get("auth_command")

    match command:
        case "download":
            try:
                config_aliases = config.basic.aliases
                aliases = raw_values.get("aliases", config_aliases)
                cli_values, no_inherit = config_values_from_cli(
                    raw_values,
                    inherited_aliases=config_aliases,
                )
                command_config = configured.with_overrides(cli_values)
                runtime = resolve_runtime_options(command_config)
                renderer.progress_enabled = not runtime.no_progress and sys.stdout.isatty()

                with bind_download_report_sink(renderer.report):
                    configure_cli(
                        no_progress=runtime.no_progress,
                        no_color=runtime.no_color,
                        debug=runtime.debug,
                    )
                    tasks = expand_download_configs(
                        command_config,
                        parser,
                        configured,
                        no_inherit=no_inherit,
                        aliases=aliases,
                        config_aliases=config_aliases,
                    )

                    if not runtime.preview_formats:
                        if runtime.ffmpeg_path is not None:
                            FFmpeg.setup_ffmpeg_path(runtime.ffmpeg_path)
                        ffmpeg = FFmpeg()
                        for task in tasks:
                            validate_download_config(task, ffmpeg)

                    credential_options = resolve_credential_options(tasks)
                    auth_list = [resolve_credentials(options) for options in credential_options]
                    auth_by_config = {id(item): auth for item, auth in zip(tasks, auth_list, strict=True)}
                    credentials_by_config = {
                        id(item): options for item, options in zip(tasks, credential_options, strict=True)
                    }

                    def resolve_config_credentials(item: ResolvedConfig) -> AuthInfo | None:
                        return auth_by_config[id(item)]

                    announced_profiles: set[tuple[Path, str]] = set()
                    inline_auth_announced = False

                    async def announce_config_auth(execution: ExecutionScope, item: ResolvedConfig) -> None:
                        nonlocal inline_auth_announced

                        options = credentials_by_config[id(item)]
                        if options.auth or options.sessdata:
                            if inline_auth_announced:
                                return
                            inline_auth_announced = True
                        else:
                            profile = (resolve_auth_file(options), options.auth_profile)
                            if profile in announced_profiles:
                                return
                            announced_profiles.add(profile)

                        await announce_cli_auth(execution, item)

                    scope_factory = RequestExecutionScopeFactory(
                        resolve_config_credentials,
                        on_open=announce_config_auth,
                    )
                    if runtime.preview_formats:
                        run_preview_formats(scope_factory, tasks, renderer)
                    else:
                        run_download(scope_factory, tasks, renderer, jobs=runtime.jobs)
            except YuttoBaseException as error:
                Logger.error(error.message)
                sys.exit(error.code.value)
            except ValueError as error:
                Logger.error(str(error))
                sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)
            except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
                Logger.info("已终止下载，再次运行即可继续下载～")
                sys.exit(ErrorCode.PAUSED_DOWNLOAD.value)

        case "auth":
            try:
                cli_values, _ = config_values_from_cli(raw_values)
                command_config = configured.with_overrides(cli_values)
                run_auth(command_config, auth_command)
            except YuttoBaseException as error:
                Logger.error(error.message)
                sys.exit(error.code.value)
            except TimeoutError as error:
                Logger.error(str(error))
                sys.exit(ErrorCode.HTTP_STATUS_ERROR.value)
            except (OSError, ValueError) as error:
                Logger.error(str(error))
                sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)

        case "serve":
            from yutto.server.command import run_server_command

            try:
                with bind_download_report_sink(renderer.report):
                    run_server_command(args, config)
            except KeyboardInterrupt:
                Logger.info("yutto server 已停止")
            except YuttoBaseException as error:
                Logger.error(error.message)
                sys.exit(error.code.value)
            except (OSError, ValueError) as error:
                Logger.error(str(error))
                sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)

        case _:
            raise ValueError("Invalid command")


@as_sync
async def run_download(
    scope_factory: ExecutionScopeFactory,
    configs: list[ResolvedConfig],
    renderer: CliApplicationEventRenderer,
    *,
    jobs: int | None = None,
) -> None:
    workflow = DownloadManager() if jobs is None else DownloadManager(jobs=jobs)
    async with renderer:
        application = YuttoApplication(
            scope_factory,
            workflow=workflow,
            event_sink=renderer,
        )
        with bind_download_report_sink(renderer.report):
            await application.download_all(configs)


async def announce_cli_auth(execution: ExecutionScope, _config: ResolvedConfig) -> None:
    if execution.session.cookie("SESSDATA") is None:
        Logger.info(
            "未提供登录认证信息，无法下载高清视频、字幕等资源哦～请通过 `--auth` 参数提供认证信息，或者先使用 `yutto auth login` 登录存储认证信息后再下载～"
        )
        return
    if await validate_user_info(execution, {"vip_status": True, "is_login": True}):
        Logger.custom("成功以大会员身份登录～", badge=Badge("大会员", fore="white", back="magenta", style=["bold"]))
    else:
        Logger.warning("以非大会员身份登录，注意无法下载会员专享剧集喔～")


if __name__ == "__main__":
    main()
