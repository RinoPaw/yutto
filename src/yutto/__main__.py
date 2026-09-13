from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from yutto.cli.auth import run_auth
from yutto.cli.auth_announcer import CliAuthAnnouncer
from yutto.cli.event_renderer import CliApplicationEventRenderer
from yutto.cli.input import expand_download_args
from yutto.cli.parser import build_parser, normalize_argv
from yutto.cli.request_adapter import download_request_from_namespace
from yutto.core.application import YuttoApplication
from yutto.core.execution import ExecutionScopeFactory, RequestExecutionScopeFactory
from yutto.core.operation import bind_download_report_sink
from yutto.download_manager import DownloadManager
from yutto.exceptions import ErrorCode, YuttoBaseException
from yutto.utils.console.logger import Logger
from yutto.utils.ffmpeg import FFmpeg
from yutto.utils.functional import as_sync
from yutto.validator import hydrate_auth, initial_validation, validate_basic_arguments

if TYPE_CHECKING:
    import argparse

    from yutto.auth import AuthInfo
    from yutto.core.request import DownloadRequest


# Compatibility aliases for code that imported these entrypoint helpers directly.
cli = build_parser
handle_default_subcommand = normalize_argv


def main() -> None:
    parser = cli()
    renderer = CliApplicationEventRenderer()
    with bind_download_report_sink(renderer.report):
        args = parser.parse_args(handle_default_subcommand(sys.argv[1:]))

    match args.command:
        case "download":
            renderer.progress_enabled = not args.no_progress and sys.stdout.isatty()
            with bind_download_report_sink(renderer.report):
                try:
                    initial_validation(args)
                    FFmpeg.setup_ffmpeg_path(args.ffmpeg_path)
                    args_list = flatten_args(args, parser)
                    auth_list = [hydrate_auth(item) for item in args_list]
                    requests = [download_request_from_namespace(item) for item in args_list]
                    credentials_by_request = {
                        id(request): auth for request, auth in zip(requests, auth_list, strict=True)
                    }

                    def resolve_credentials(request: DownloadRequest) -> AuthInfo | None:
                        return credentials_by_request[id(request)]

                    scope_factory = RequestExecutionScopeFactory(
                        resolve_credentials,
                        on_open=CliAuthAnnouncer(),
                    )
                    run_download(scope_factory, requests, renderer, jobs=args.jobs)
                except YuttoBaseException as error:
                    Logger.error(error.message)
                    sys.exit(error.code.value)
                except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
                    Logger.info("已终止下载，再次运行即可继续下载～")
                    sys.exit(ErrorCode.PAUSED_DOWNLOAD.value)

        case "auth":
            run_auth(args)

        case "serve":
            from yutto.server.command import run_server_command

            try:
                with bind_download_report_sink(renderer.report):
                    run_server_command(args)
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


def flatten_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[argparse.Namespace]:
    """Compatibility wrapper around the CLI input-expansion layer."""
    return expand_download_args(args, parser, validate=validate_basic_arguments)


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


if __name__ == "__main__":
    main()
