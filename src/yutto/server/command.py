from __future__ import annotations

import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yutto.auth import default_auth_file
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.settings import scope_from_config
from yutto.core.application import YuttoApplication
from yutto.core.execution import resolve_download_workers, resolve_fetch_workers
from yutto.core.task_service import DownloadTaskService, ResolveTaskService
from yutto.download_manager import DownloadManager
from yutto.downloader.path_leases import DownloadPathLeasePool
from yutto.runtime import TaskCapacityPool, monotonic_seq_allocator
from yutto.server.request import scope_parser_from_settings
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
    options: Any,
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
    parse_scope = scope_parser_from_settings(options.request_settings)
    default_scope = parse_scope({"source": {"url": "yutto-server-default-validation"}})
    prepared_default = policy.prepare_scope(default_scope)
    policy.resolve_credentials(prepared_default)
    scope_factory = policy.build_scope_factory()

    event_seq_allocator = monotonic_seq_allocator()
    task_capacity = TaskCapacityPool(options.task_limit)
    path_leases = DownloadPathLeasePool()

    def build_download_application(
        factory: ExecutionScopeFactory,
        event_sink: DownloadEventSink,
    ) -> YuttoApplication:
        return _build_download_application(factory, event_sink, path_leases=path_leases)

    task_service = DownloadTaskService(
        scope_factory,
        build_download_application,
        task_limit=options.task_limit,
        worker_count=options.jobs,
        seq_allocator=event_seq_allocator,
        capacity_pool=task_capacity,
    )
    resolve_service = ResolveTaskService(
        scope_factory,
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
        prepare_scope=policy.prepare_scope,
        parse_scope=parse_scope,
        resolve_service=resolve_service,
    )


def _build_download_application(
    scope_factory: ExecutionScopeFactory,
    event_sink: DownloadEventSink,
    *,
    path_leases: DownloadPathLeasePool | None = None,
) -> YuttoApplication:
    manager = DownloadManager(path_leases=path_leases)
    return YuttoApplication(
        scope_factory,
        workflow=manager,
        event_sink=event_sink,
        resolve_workflow=manager,
    )


@as_sync
async def run_server_command(args: argparse.Namespace, settings: YuttoConfig) -> None:
    values = vars(args)
    configured_scope = scope_from_config(settings)
    configured_runtime = resolve_runtime_options(configured_scope)
    configured_fetch_workers = resolve_fetch_workers(configured_scope)
    configured_download_workers = resolve_download_workers(configured_scope)

    values.setdefault("request_settings", settings)
    values.setdefault("ffmpeg_path", configured_runtime.ffmpeg_path or "ffmpeg")
    values.setdefault("host", "127.0.0.1")
    values.setdefault("port", 11223)
    values.setdefault("allow_origin", ())
    values.setdefault("token_file", None)
    values.setdefault(
        "download_root",
        Path(settings.basic.dir).expanduser() if settings.basic.dir is not None else Path(),
    )
    values.setdefault(
        "tmp_root",
        None if settings.basic.tmp_dir is None else Path(settings.basic.tmp_dir).expanduser(),
    )
    values.setdefault(
        "auth_file",
        None if settings.auth.auth_file is None else Path(settings.auth.auth_file).expanduser(),
    )
    values.setdefault("max_fetch_workers", max(16, configured_fetch_workers))
    values.setdefault("max_download_workers", max(16, configured_download_workers))
    values.setdefault("task_limit", 256)
    values.setdefault("jobs", configured_runtime.jobs)

    args.port = int(args.port)
    args.max_fetch_workers = int(args.max_fetch_workers)
    args.max_download_workers = int(args.max_download_workers)
    args.task_limit = int(args.task_limit)
    args.jobs = int(args.jobs)
    args.allow_origin = tuple(args.allow_origin)

    if args.jobs < 1:
        raise ValueError("jobs 应为不小于 1 的整数")
    if args.max_fetch_workers < 1 or args.max_download_workers < 1:
        raise ValueError("server worker 上限应为不小于 1 的整数")
    if args.task_limit < 1:
        raise ValueError("task_limit 应为不小于 1 的整数")

    FFmpeg.setup_ffmpeg_path(str(args.ffmpeg_path))
    ffmpeg = FFmpeg()
    token = resolve_server_token(args.token_file)
    server = build_server(args, token.value, ffmpeg=ffmpeg)
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
