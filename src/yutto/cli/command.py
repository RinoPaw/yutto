from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.cli.request_adapter import merge_request_patches, request_overrides_from_namespace, resolve_download_request

if TYPE_CHECKING:
    import argparse
    from typing import Any

    from yutto.cli.settings import YuttoSettings
    from yutto.core.request import DownloadRequest


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
    sessdata: str = ""


@dataclass(frozen=True, slots=True)
class DownloadRuntimeOptions:
    """Process-wide CLI behavior for one download invocation."""

    ffmpeg_path: str
    jobs: int
    no_color: bool
    no_progress: bool
    debug: bool


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
    mode: str = "terminal"
    poll_interval: float = 2.0
    timeout: int = 180


@dataclass(frozen=True, slots=True)
class ServeCommand:
    server_settings: YuttoSettings
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


def download_layer_from_namespace(args: argparse.Namespace) -> DownloadLayer:
    values = vars(args)
    source = values.get("source", values.get("url"))
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
    jobs = int(values.get("jobs", settings.basic.jobs))
    if jobs < 1:
        raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）")
    return DownloadRuntimeOptions(
        ffmpeg_path=str(values.get("ffmpeg_path", "ffmpeg")),
        jobs=jobs,
        no_color=bool(values.get("no_color", settings.basic.no_color)),
        no_progress=bool(values.get("no_progress", settings.basic.no_progress)),
        debug=bool(values.get("debug", settings.basic.debug)),
    )


def resolve_download_command(layer: DownloadLayer, settings: YuttoSettings) -> DownloadCommand:
    request = resolve_download_request(layer.source, settings, layer.request_overrides)
    values: dict[str, Any] = {
        "auth": settings.auth.auth,
        "auth_file": _optional_path(settings.auth.auth_file),
        "auth_profile": settings.auth.auth_profile,
        "sessdata": settings.basic.sessdata,
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
    return AuthCommand(
        auth_command=values["auth_command"],
        auth=str(values.get("auth", settings.auth.auth)),
        auth_file=values.get("auth_file", _optional_path(settings.auth.auth_file)),
        auth_profile=str(values.get("auth_profile", settings.auth.auth_profile)),
        proxy=str(values.get("proxy", settings.basic.proxy)),
        mode=str(values.get("mode", "terminal")),
        poll_interval=float(values.get("poll_interval", 2.0)),
        timeout=int(values.get("timeout", 180)),
    )


def resolve_serve_command(args: argparse.Namespace, settings: YuttoSettings) -> ServeCommand:
    values = vars(args)
    jobs = int(values.get("jobs", settings.basic.jobs))
    max_fetch_workers = int(values.get("max_fetch_workers", max(16, settings.basic.fetch_workers)))
    max_download_workers = int(values.get("max_download_workers", max(16, settings.basic.num_workers)))
    task_limit = int(values.get("task_limit", 256))
    if jobs < 1:
        raise ValueError("jobs 应为不小于 1 的整数")
    if max_fetch_workers < 1 or max_download_workers < 1:
        raise ValueError("server worker 上限应为不小于 1 的整数")
    if task_limit < 1:
        raise ValueError("task_limit 应为不小于 1 的整数")

    return ServeCommand(
        server_settings=settings,
        ffmpeg_path=str(values.get("ffmpeg_path", "ffmpeg")),
        host=str(values.get("host", "127.0.0.1")),
        port=int(values.get("port", 11223)),
        allow_origin=tuple(values.get("allow_origin", ())),
        token_file=values.get("token_file"),
        download_root=values.get("download_root", Path(settings.basic.dir).expanduser()),
        tmp_root=values.get("tmp_root", _optional_path(settings.basic.tmp_dir)),
        auth_file=values.get("auth_file", _optional_path(settings.auth.auth_file)),
        max_fetch_workers=max_fetch_workers,
        max_download_workers=max_download_workers,
        task_limit=task_limit,
        jobs=jobs,
    )


def _optional_path(value: str | None) -> Path | None:
    return None if value is None else Path(value).expanduser()
