from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from yutto.auth import resolve_auth_file, validate_user_info
from yutto.cli.auth import run_auth
from yutto.cli.bootstrap import load_cli_settings, parse_bootstrap_args
from yutto.cli.command import (
    download_layer_from_namespace,
    resolve_auth_command,
    resolve_download_command,
    resolve_download_runtime_options,
    resolve_serve_command,
)
from yutto.cli.compat import normalize_argv
from yutto.cli.event_renderer import CliApplicationEventRenderer
from yutto.cli.formats import run_preview_formats
from yutto.cli.input import expand_download_layers
from yutto.cli.parser import build_parser
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
    from pathlib import Path

    from yutto.auth import AuthInfo
    from yutto.core.execution import ExecutionScope
    from yutto.core.request import DownloadRequest


def main() -> None:
    raw_argv = sys.argv[1:]
    try:
        settings = load_cli_settings(parse_bootstrap_args(raw_argv))
    except (OSError, ValueError) as error:
        Logger.error(str(error))
        sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)

    parser = build_parser()
    renderer = CliApplicationEventRenderer()
    with bind_download_report_sink(renderer.report):
        args = parser.parse_args(normalize_argv(raw_argv))

    match args.command:
        case "download":
            try:
                runtime = resolve_download_runtime_options(args, settings)
                preview_formats = bool(getattr(args, "preview_formats", False))
                renderer.progress_enabled = not runtime.no_progress and sys.stdout.isatty()

                with bind_download_report_sink(renderer.report):
                    configure_cli(runtime)
                    outer_layer = download_layer_from_namespace(args)
                    outer_command = resolve_download_command(outer_layer, settings)

                    if not preview_formats:
                        FFmpeg.setup_ffmpeg_path(runtime.ffmpeg_path)
                        ffmpeg = FFmpeg()
                        validate_download_request(outer_command.request, ffmpeg)

                    layers = expand_download_layers(outer_layer, parser, settings)
                    commands = [resolve_download_command(layer, settings) for layer in layers]
                    if not preview_formats:
                        for command in commands:
                            validate_download_request(command.request, ffmpeg)

                    auth_list = [resolve_credentials(command.credentials) for command in commands]
                    requests = [command.request for command in commands]
                    auth_by_request = {id(request): auth for request, auth in zip(requests, auth_list, strict=True)}
                    credential_options_by_request = {id(command.request): command.credentials for command in commands}

                    def resolve_request_credentials(request: DownloadRequest) -> AuthInfo | None:
                        return auth_by_request[id(request)]

                    announced_profiles: set[tuple[Path, str]] = set()
                    inline_auth_announced = False

                    async def announce_request_auth(scope: ExecutionScope, request: DownloadRequest) -> None:
                        nonlocal inline_auth_announced

                        options = credential_options_by_request[id(request)]
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
                        run_download(scope_factory, requests, renderer, jobs=runtime.jobs)
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
            run_auth(resolve_auth_command(args, settings))

        case "serve":
            from yutto.server.command import run_server_command

            try:
                with bind_download_report_sink(renderer.report):
                    run_server_command(resolve_serve_command(args, settings))
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
