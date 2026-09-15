from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.cli.request_adapter import merge_request_patches, request_overrides_from_namespace, resolve_download_request
from yutto.core.request import AccessSpec, NetworkSpec, OutputSpec

if TYPE_CHECKING:
    import argparse
    from typing import Any

    from yutto.cli.settings import YuttoSettings
    from yutto.core.request import DownloadRequest


DEFAULT_FFMPEG_PATH = "ffmpeg"
DEFAULT_JOBS = 1
DEFAULT_NO_COLOR = False
DEFAULT_NO_PROGRESS = False
DEFAULT_DEBUG = False
DEFAULT_AUTH = ""
DEFAULT_SESSDATA = ""
DEFAULT_AUTH_MODE = "terminal"
DEFAULT_AUTH_POLL_INTERVAL = 2.0
DEFAULT_AUTH_TIMEOUT = 180
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 11223
DEFAULT_SERVER_WORKER_LIMIT = 16
DEFAULT_SERVER_TASK_LIMIT = 256

_DEFAULT_ACCESS = AccessSpec()
_DEFAULT_NETWORK = NetworkSpec()
_DEFAULT_OUTPUT = OutputSpec()


@dataclass(frozen=True, slots=True)
class DownloadLayer:
    """One explicit per-task CLI layer before settings/default resolution."""

    source: str
    request_overrides: dict[str, Any]
    cli_overrides: dict[str, Any]
    no_inherit: bool = False


@dataclass(frozen=True, slots=True)
class CredentialOptions:
    auth: str
    auth_file: Path | None
    auth_profile: str
    sessdata: str = DEFAULT_SESSDATA


@dataclass(frozen=True, slots=True)
class DownloadRuntimeOptions:
    """Process-wide CLI behavior for one download invocation."""

    ffmpeg_path: str = DEFAULT_FFMPEG_PATH
    jobs: int = DEFAULT_JOBS
    no_color: bool = DEFAULT_NO_COLOR
    no_progress: bool = DEFAULT_NO_PROGRESS
    debug: bool = DEFAULT_DEBUG


@dataclass(frozen=True, slots=True)
class DownloadCommand:
    request: DownloadRequest
    credentials: CredentialOptions


@dataclass(frozen=True, slots=True)
class AuthCommand:
    auth_command: str
    auth: str
    auth_file: Path | None
    auth_profile: str
    proxy: str
    mode: str = DEFAULT_AUTH_MODE
    poll_interval: float = DEFAULT_AUTH_POLL_INTERVAL
    timeout: int = DEFAULT_AUTH_TIMEOUT


@dataclass(frozen=True, slots=True)
class ServeCommand:
    request_settings: YuttoSettings
    ffmpeg_path: str = DEFAULT_FFMPEG_PATH
    host: str = DEFAULT_SERVER_HOST
    port: int = DEFAULT_SERVER_PORT
    allow_origin: tuple[str, ...] = ()
    token_file: Path | None = None
    download_root: Path = _DEFAULT_OUTPUT.directory
    tmp_root: Path | None = _DEFAULT_OUTPUT.temporary_directory
    auth_file: Path | None = None
    max_fetch_workers: int = DEFAULT_SERVER_WORKER_LIMIT
    max_download_workers: int = DEFAULT_SERVER_WORKER_LIMIT
    task_limit: int = DEFAULT_SERVER_TASK_LIMIT
    jobs: int = DEFAULT_JOBS


def download_layer_from_namespace(args: argparse.Namespace) -> DownloadLayer:
    values = vars(args)
    source = values.get("source")
    if source is None:
        raise ValueError("download source is missing")

    cli_overrides: dict[str, Any] = {}
    for name in ("auth", "auth_file", "auth_profile", "sessdata", "aliases"):
        if name in values:
            cli_overrides[name] = values[name]

    return DownloadLayer(
        source=str(source),
        request_overrides=request_overrides_from_namespace(args),
        cli_overrides=cli_overrides,
        no_inherit=bool(values.get("no_inherit", False)),
    )


def merge_download_layers(parent: DownloadLayer, child: DownloadLayer) -> DownloadLayer:
    cli_overrides = dict(parent.cli_overrides)
    cli_overrides.update(child.cli_overrides)
    return DownloadLayer(
        source=child.source,
        request_overrides=merge_request_patches(parent.request_overrides, child.request_overrides),
        cli_overrides=cli_overrides,
        no_inherit=child.no_inherit,
    )


def resolve_download_runtime_options(
    args: argparse.Namespace,
    settings: YuttoSettings,
) -> DownloadRuntimeOptions:
    values = vars(args)
    configured_jobs = settings.basic.jobs if settings.basic.jobs is not None else DEFAULT_JOBS
    jobs = int(values.get("jobs", configured_jobs))
    if jobs < 1:
        raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）")

    configured_no_color = settings.basic.no_color if settings.basic.no_color is not None else DEFAULT_NO_COLOR
    configured_no_progress = (
        settings.basic.no_progress if settings.basic.no_progress is not None else DEFAULT_NO_PROGRESS
    )
    configured_debug = settings.basic.debug if settings.basic.debug is not None else DEFAULT_DEBUG

    return DownloadRuntimeOptions(
        ffmpeg_path=str(values.get("ffmpeg_path", DEFAULT_FFMPEG_PATH)),
        jobs=jobs,
        no_color=bool(values.get("no_color", configured_no_color)),
        no_progress=bool(values.get("no_progress", configured_no_progress)),
        debug=bool(values.get("debug", configured_debug)),
    )


def resolve_download_command(layer: DownloadLayer, settings: YuttoSettings) -> DownloadCommand:
    request = resolve_download_request(layer.source, settings, layer.request_overrides)
    values: dict[str, Any] = {
        "auth": settings.auth.auth if settings.auth.auth is not None else DEFAULT_AUTH,
        "auth_file": _optional_path(settings.auth.auth_file),
        "auth_profile": (
            settings.auth.auth_profile if settings.auth.auth_profile is not None else _DEFAULT_ACCESS.auth_profile
        ),
        "sessdata": settings.basic.sessdata if settings.basic.sessdata is not None else DEFAULT_SESSDATA,
    }
    values.update(layer.cli_overrides)

    return DownloadCommand(
        request=request,
        credentials=CredentialOptions(
            auth=str(values["auth"]),
            auth_file=values["auth_file"],
            auth_profile=str(values["auth_profile"]),
            sessdata=str(values["sessdata"]),
        ),
    )


def resolve_auth_command(args: argparse.Namespace, settings: YuttoSettings) -> AuthCommand:
    values = vars(args)
    configured_auth = settings.auth.auth if settings.auth.auth is not None else DEFAULT_AUTH
    configured_profile = (
        settings.auth.auth_profile if settings.auth.auth_profile is not None else _DEFAULT_ACCESS.auth_profile
    )
    configured_proxy = settings.basic.proxy if settings.basic.proxy is not None else _DEFAULT_NETWORK.proxy

    return AuthCommand(
        auth_command=str(values["auth_command"]),
        auth=str(values.get("auth", configured_auth)),
        auth_file=values.get("auth_file", _optional_path(settings.auth.auth_file)),
        auth_profile=str(values.get("auth_profile", configured_profile)),
        proxy=str(values.get("proxy", configured_proxy)),
        mode=str(values.get("mode", DEFAULT_AUTH_MODE)),
        poll_interval=float(values.get("poll_interval", DEFAULT_AUTH_POLL_INTERVAL)),
        timeout=int(values.get("timeout", DEFAULT_AUTH_TIMEOUT)),
    )


def resolve_serve_command(args: argparse.Namespace, settings: YuttoSettings) -> ServeCommand:
    values = vars(args)

    configured_jobs = settings.basic.jobs if settings.basic.jobs is not None else DEFAULT_JOBS
    configured_fetch_workers = (
        settings.basic.fetch_workers if settings.basic.fetch_workers is not None else _DEFAULT_NETWORK.fetch_workers
    )
    configured_download_workers = (
        settings.basic.num_workers if settings.basic.num_workers is not None else _DEFAULT_NETWORK.download_workers
    )
    configured_download_root = (
        Path(settings.basic.dir).expanduser() if settings.basic.dir is not None else _DEFAULT_OUTPUT.directory
    )
    configured_tmp_root = _optional_path(settings.basic.tmp_dir)
    configured_auth_file = _optional_path(settings.auth.auth_file)

    jobs = int(values.get("jobs", configured_jobs))
    max_fetch_workers = int(
        values.get("max_fetch_workers", max(DEFAULT_SERVER_WORKER_LIMIT, configured_fetch_workers))
    )
    max_download_workers = int(
        values.get("max_download_workers", max(DEFAULT_SERVER_WORKER_LIMIT, configured_download_workers))
    )
    task_limit = int(values.get("task_limit", DEFAULT_SERVER_TASK_LIMIT))

    if jobs < 1:
        raise ValueError("jobs 应为不小于 1 的整数")
    if max_fetch_workers < 1 or max_download_workers < 1:
        raise ValueError("server worker 上限应为不小于 1 的整数")
    if task_limit < 1:
        raise ValueError("task_limit 应为不小于 1 的整数")

    return ServeCommand(
        request_settings=settings,
        ffmpeg_path=str(values.get("ffmpeg_path", DEFAULT_FFMPEG_PATH)),
        host=str(values.get("host", DEFAULT_SERVER_HOST)),
        port=int(values.get("port", DEFAULT_SERVER_PORT)),
        allow_origin=tuple(values.get("allow_origin", ())),
        token_file=values.get("token_file"),
        download_root=values.get("download_root", configured_download_root),
        tmp_root=values.get("tmp_root", configured_tmp_root),
        auth_file=values.get("auth_file", configured_auth_file),
        max_fetch_workers=max_fetch_workers,
        max_download_workers=max_download_workers,
        task_limit=task_limit,
        jobs=jobs,
    )


def _optional_path(value: str | None) -> Path | None:
    return None if value is None else Path(value).expanduser()
