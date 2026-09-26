from __future__ import annotations

import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.auth import default_auth_file
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.settings import resolved_config_from_settings
from yutto.core.application import YuttoApplication
from yutto.core.execution import resolve_download_workers, resolve_fetch_workers
from yutto.core.task_service import DownloadTaskService, ResolveTaskService
from yutto.download_manager import DownloadManager
from yutto.downloader.path_leases import DownloadPathLeasePool
from yutto.runtime import TaskCapacityPool, monotonic_seq_allocator
from yutto.server.request import config_parser_from_settings
from yutto.server.service import ServerPolicy, ServerPolicyOptions
from yutto.server.websocket import WebSocketServerOptions, YuttoWebSocketServer
from yutto.utils.console.logger import Logger
from yutto.utils.ffmpeg import FFmpeg
from yutto.utils.functional import as_sync

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping

    from yutto.cli.settings import YuttoConfig
    from yutto.core.events import DownloadEventSink
    from yutto.core.execution import ExecutionScopeFactory


@dataclass(frozen=True, slots=True)
class ServerToken:
    value: str
    generated: bool
    persisted_to: Path | None = None


@dataclass(frozen=True, slots=True)
class ServeOptions:
    """Resolved process-level configuration for one server invocation."""

    request_settings: YuttoConfig
    ffmpeg_path: str
    host: str
    port: int
    allow_origin: tuple[str, ...]
    token_file: Path | None
    download_root: Path
    tmp_root: Path | None
    auth_file: Path | None
    max_fetch_workers: int
    max_download_workers: int
    task_limit: int
    jobs: int


def resolve_serve_options(args: argparse.Namespace, settings: YuttoConfig) -> ServeOptions:
    """Resolve sparse CLI overrides and persistent settings into server startup facts."""

    values = vars(args)
    configured = resolved_config_from_settings(settings)
    runtime = resolve_runtime_options(values, settings)
    configured_fetch_workers = resolve_fetch_workers(configured)
    configured_download_workers = resolve_download_workers(configured)

    configured_download_root = Path(configured.output.directory).expanduser()
    configured_tmp_root = configured.output.temporary_directory
    configured_auth_file = configured.auth.file

    options = ServeOptions(
        request_settings=settings,
        ffmpeg_path=runtime.ffmpeg_path or "ffmpeg",
        host=str(values.get("host", "127.0.0.1")),
        port=int(values.get("port", 11223)),
        allow_origin=tuple(values.get("allow_origin", ())),
        token_file=values.get("token_file"),
        download_root=Path(values.get("download_root", configured_download_root)).expanduser(),
        tmp_root=(
            Path(values["tmp_root"]).expanduser()
            if "tmp_root" in values
            else None
            if configured_tmp_root is None
            else Path(configured_tmp_root).expanduser()
        ),
        auth_file=(
            Path(values["auth_file"]).expanduser()
            if "auth_file" in values
            else None
            if configured_auth_file is None
            else Path(configured_auth_file).expanduser()
        ),
        max_fetch_workers=int(values.get("max_fetch_workers", max(16, configured_fetch_workers))),
        max_download_workers=int(values.get("max_download_workers", max(16, configured_download_workers))),
        task_limit=int(values.get("task_limit", 256)),
        jobs=runtime.jobs,
    )

    if options.jobs < 1:
        raise ValueError("jobs 应为不小于 1 的整数")
    if options.max_fetch_workers < 1 or options.max_download_workers < 1:
        raise ValueError("server worker 上限应为不小于 1 的整数")
    if options.task_limit < 1:
        raise ValueError("task_limit 应为不小于 1 的整数")
    return options


def resolve_server_token(
    token_file: Path | None,
    *,
    environ: Mapping[str, str] | None = None,
) -> ServerToken:
    environment = os.environ if environ is None else environ
    environment_token = environment.get("YUTTO_SERVER_TOKEN", "").strip()
    if environment_token:
        return ServerToken(environment_token, generated=False)

    if token_file is not None:
        try:
            token = _read_server_token(token_file)
        except FileNotFoundError:
            pass
        else:
            return ServerToken(token, generated=False, persisted_to=token_file)

    token = secrets.token_urlsafe(32)
    if token_file is None:
        return ServerToken(token, generated=True)

    token_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            token_file,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        existing_token = _read_server_token(token_file)
        return ServerToken(existing_token, generated=False, persisted_to=token_file)
    with os.fdopen(descriptor, "w", encoding="utf-8") as token_stream:
        token_stream.write(token + "\n")
    return ServerToken(token, generated=True, persisted_to=token_file)


def _read_server_token(token_file: Path) -> str:
    try:
        descriptor = os.open(token_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        raise
    except OSError as error:
        raise ValueError(f"无法安全读取 server token 文件：{token_file}") from error

    with os.fdopen(descriptor, encoding="utf-8") as token_stream:
        metadata = os.fstat(token_stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"server token 路径不是普通文件：{token_file}")
        if os.name != "nt" and metadata.st_mode & 0o077:
            raise ValueError(f"server token 文件权限过宽，请执行 chmod 600：{token_file}")
        token = token_stream.read().strip()
    if not token:
        raise ValueError(f"server token 文件为空：{token_file}")
    return token


def build_server(
    options: ServeOptions,
    token: str,
    *,
    ffmpeg: FFmpeg | None = None,
) -> YuttoWebSocketServer:
    ffmpeg = ffmpeg or FFmpeg()
    policy = ServerPolicy(
        ServerPolicyOptions(
            download_root=options.download_root,
            tmp_root=options.tmp_root or options.download_root,
            auth_file=options.auth_file or default_auth_file(),
            max_fetch_workers=options.max_fetch_workers,
            max_download_workers=options.max_download_workers,
            allowed_video_save_codecs=frozenset([*ffmpeg.video_encodecs, "copy"]),
            allowed_audio_save_codecs=frozenset([*ffmpeg.audio_encodecs, "copy"]),
        )
    )
    parse_config = config_parser_from_settings(options.request_settings)
    default_config = parse_config({"source": {"url": "yutto-server-default-validation"}})
    prepared_default = policy.prepare_config(default_config)
    policy.resolve_credentials(prepared_default)
    execution_factory = policy.build_execution_factory()

    event_seq_allocator = monotonic_seq_allocator()
    task_capacity = TaskCapacityPool(options.task_limit)
    path_leases = DownloadPathLeasePool()

    def build_download_application(
        factory: ExecutionScopeFactory,
        event_sink: DownloadEventSink,
    ) -> YuttoApplication:
        return _build_download_application(factory, event_sink, path_leases=path_leases)

    task_service = DownloadTaskService(
        execution_factory,
        build_download_application,
        task_limit=options.task_limit,
        worker_count=options.jobs,
        seq_allocator=event_seq_allocator,
        capacity_pool=task_capacity,
    )
    resolve_service = ResolveTaskService(
        execution_factory,
        build_download_application,
        task_limit=options.task_limit,
        seq_allocator=event_seq_allocator,
        capacity_pool=task_capacity,
    )
    return YuttoWebSocketServer(
        task_service,
        WebSocketServerOptions(
            token=token,
            host=options.host,
            port=options.port,
            allowed_origins=options.allow_origin,
        ),
        prepare_config=policy.prepare_config,
        parse_config=parse_config,
        resolve_service=resolve_service,
    )


def _build_download_application(
    execution_factory: ExecutionScopeFactory,
    event_sink: DownloadEventSink,
    *,
    path_leases: DownloadPathLeasePool | None = None,
) -> YuttoApplication:
    manager = DownloadManager(path_leases=path_leases)
    return YuttoApplication(
        execution_factory,
        workflow=manager,
        event_sink=event_sink,
        resolve_workflow=manager,
    )


@as_sync
async def run_server_command(args: argparse.Namespace, settings: YuttoConfig) -> None:
    options = resolve_serve_options(args, settings)

    FFmpeg.setup_ffmpeg_path(options.ffmpeg_path)
    ffmpeg = FFmpeg()
    token = resolve_server_token(options.token_file)
    server = build_server(options, token.value, ffmpeg=ffmpeg)
    await server.start()
    for socket in server.sockets:
        address = socket.getsockname()
        display_host = f"[{address[0]}]" if ":" in address[0] else address[0]
        Logger.info(f"yutto server 正在监听 ws://{display_host}:{address[1]}")
    if token.persisted_to is not None:
        Logger.info(f"server token 文件：{token.persisted_to}")
    elif token.generated:
        Logger.info(f"本次 server token：{token.value}")
    try:
        await server.serve_forever()
    finally:
        await server.close(cancel_pending=True)
