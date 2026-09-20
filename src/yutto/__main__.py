from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.auth import resolve_auth_file, validate_user_info
from yutto.cli.auth import run_auth
from yutto.cli.compat import normalize_argv
from yutto.cli.event_renderer import CliApplicationEventRenderer
from yutto.cli.formats import run_preview_formats
from yutto.cli.input import expand_download_values
from yutto.cli.parser import build_parser
from yutto.cli.request_adapter import resolve_download_request
from yutto.cli.settings import YuttoSettings, load_settings_file, search_for_settings_file
from yutto.core.application import YuttoApplication
from yutto.core.execution import ExecutionScopeFactory, RequestExecutionScopeFactory
from yutto.core.operation import bind_download_report_sink
from yutto.download_manager import DownloadManager
from yutto.exceptions import ErrorCode, YuttoBaseException
from yutto.utils.console.logger import Badge, Logger
from yutto.utils.ffmpeg import FFmpeg
from yutto.utils.functional import as_sync
from yutto.validator import configure_cli, resolve_credentials, validate_download_request

if TYPE_CHECKING:
    from yutto.auth import AuthInfo
    from yutto.core.execution import ExecutionScope
    from yutto.core.request import DownloadRequest


def main() -> None:
    parser = build_parser()
    renderer = CliApplicationEventRenderer()
    args = parser.parse_args(normalize_argv(sys.argv[1:]))

    settings: YuttoSettings
    try:
        config = getattr(args, "config", None)
        config = Path(config).expanduser() if config is not None else search_for_settings_file()
        if config is None:
            settings = YuttoSettings()
        else:
            Logger.info(f"发现配置文件 {config}，加载中……")
            settings = load_settings_file(config)
    except (OSError, ValueError) as error:
        Logger.error(str(error))
        sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)

    match args.command:
        case "download":
            try:
                values = vars(args)
                jobs = int(values.get("jobs", settings.basic.jobs if settings.basic.jobs is not None else 1))
                if jobs < 1:
                    raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）")

                no_color = bool(
                    values.get("no_color", settings.basic.no_color if settings.basic.no_color is not None else False)
                )
                no_progress = bool(
                    values.get(
                        "no_progress",
                        settings.basic.no_progress if settings.basic.no_progress is not None else False,
                    )
                )
                debug = bool(values.get("debug", settings.basic.debug if settings.basic.debug is not None else False))
                ffmpeg_path = str(values.get("ffmpeg_path", "ffmpeg"))
                preview_formats = bool(values.get("preview_formats", False))
                renderer.progress_enabled = not no_progress and sys.stdout.isatty()

                with bind_download_report_sink(renderer.report):
                    configure_cli(no_progress=no_progress, no_color=no_color, debug=debug)
                    tasks = expand_download_values(values, parser, settings)
                    requests = [resolve_download_request(task, settings) for task in tasks]

                    if not preview_formats:
                        FFmpeg.setup_ffmpeg_path(ffmpeg_path)
                        ffmpeg = FFmpeg()
                        for request in requests:
                            validate_download_request(request, ffmpeg)

                    configured_auth = settings.auth.auth if settings.auth.auth is not None else ""
                    configured_auth_file = (
                        None if settings.auth.auth_file is None else Path(settings.auth.auth_file).expanduser()
                    )
                    configured_auth_profile = (
                        settings.auth.auth_profile if settings.auth.auth_profile is not None else "default"
                    )
                    configured_sessdata = settings.basic.sessdata if settings.basic.sessdata is not None else ""
                    credential_options = [
                        argparse.Namespace(
                            auth=str(task.get("auth", configured_auth)),
                            auth_file=task.get("auth_file", configured_auth_file),
                            auth_profile=str(task.get("auth_profile", configured_auth_profile)),
                            sessdata=str(task.get("sessdata", configured_sessdata)),
                        )
                        for task in tasks
                    ]
                    auth_list = [resolve_credentials(options) for options in credential_options]
                    auth_by_request = {id(request): auth for request, auth in zip(requests, auth_list, strict=True)}
                    credentials_by_request = {
                        id(request): options
                        for request, options in zip(requests, credential_options, strict=True)
                    }

                    def resolve_request_credentials(request: DownloadRequest) -> AuthInfo | None:
                        return auth_by_request[id(request)]

                    announced_profiles: set[tuple[Path, str]] = set()
                    inline_auth_announced = False

                    async def announce_request_auth(scope: ExecutionScope, request: DownloadRequest) -> None:
                        nonlocal inline_auth_announced

                        options = credentials_by_request[id(request)]
                        if options.auth or options.sessdata:
                            if inline_auth_announced:
                                return
                            inline_auth_announced = True
                        else:
                            profile = (resolve_auth_file(options), options.auth_profile)
                            if profile in announced_profiles:
                                return
                            announced_profiles.add(profile)

                        await announce_cli_auth(scope, request)

                    scope_factory = RequestExecutionScopeFactory(
                        resolve_request_credentials,
                        on_open=announce_request_auth,
                    )
                    if preview_formats:
                        run_preview_formats(scope_factory, requests, renderer)
                    else:
                        run_download(scope_factory, requests, renderer, jobs=jobs)
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
                run_auth(args, settings)
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
                    run_server_command(args, settings)
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
    requests: list[DownloadRequest],
    renderer: CliApplicationEventRenderer,
    *,
    jobs: int = 1,
) -> None:
    async with renderer:
        application = YuttoApplication(
            scope_factory,
            workflow=DownloadManager(jobs=jobs),
            event_sink=renderer,
        )
        with bind_download_report_sink(renderer.report):
            await application.download_all(requests)


async def announce_cli_auth(scope: ExecutionScope, _request: DownloadRequest) -> None:
    if scope.session.cookie("SESSDATA") is None:
        Logger.info(
            "未提供登录认证信息，无法下载高清视频、字幕等资源哦～请通过 `--auth` 参数提供认证信息，或者先使用 `yutto auth login` 登录存储认证信息后再下载～"
        )
        return
    if await validate_user_info(scope, {"vip_status": True, "is_login": True}):
        Logger.custom("成功以大会员身份登录～", badge=Badge("大会员", fore="white", back="magenta", style=["bold"]))
    else:
        Logger.warning("以非大会员身份登录，注意无法下载会员专享剧集喔～")


if __name__ == "__main__":
    main()
