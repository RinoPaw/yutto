from __future__ import annotations

from typing import TYPE_CHECKING, cast

from yutto.cli.scope import MISSING, Scope, config_scope
from yutto.core.request import DownloadRequest

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Any

    from yutto.cli.settings import YuttoConfig

MEBIBYTE = 1024 * 1024


def request_overrides_from_scope(
    scope: Scope,
    *,
    include_output_paths: bool = True,
) -> dict[str, Any]:
    """Translate resolved CLI/config scope values into a frontend-independent request patch."""

    request: dict[str, Any] = {}

    access: dict[str, Any] = {}
    _copy_value(scope, access, "auth_profile")
    _copy_value(scope, access, "login_strict")
    _copy_value(scope, access, "vip_strict")
    if access:
        request["access"] = access

    selection: dict[str, Any] = {}
    selection_expr = scope.lookup("selection_expr")
    batch = scope.lookup("batch")
    if selection_expr is not MISSING:
        selection["expression"] = selection_expr
    elif batch is not MISSING and batch:
        selection["expression"] = "~"
    _copy_value(scope, selection, "skip_preview")
    _copy_value(scope, selection, "publication_start_time", "start_time")
    _copy_value(scope, selection, "publication_end_time", "end_time")
    if selection:
        request["selection"] = selection

    with_extra_episodes = scope.lookup("with_extra_episodes")
    if with_extra_episodes is not MISSING:
        request["with_extra_episodes"] = with_extra_episodes

    resources: dict[str, Any] = {}
    for scope_name, request_name in (
        ("require_video", "video"),
        ("require_audio", "audio"),
        ("require_danmaku", "danmaku"),
        ("require_subtitle", "subtitle"),
        ("require_metadata", "metadata"),
        ("require_cover", "cover"),
        ("require_chapter_info", "chapter_info"),
        ("save_cover", "save_cover"),
        ("ai_translation_language", "ai_translation_language"),
    ):
        _copy_value(scope, resources, scope_name, request_name)
    if resources:
        request["resources"] = resources

    stream: dict[str, Any] = {}
    _copy_value(scope, stream, "video_quality")
    _copy_value(scope, stream, "audio_quality")

    vcodec = scope.lookup("vcodec")
    if vcodec is not MISSING:
        stream["video_download_codec"], stream["video_save_codec"] = _split_codec_pair(vcodec, "vcodec")

    acodec = scope.lookup("acodec")
    if acodec is not MISSING:
        stream["audio_download_codec"], stream["audio_save_codec"] = _split_codec_pair(acodec, "acodec")

    _copy_value(scope, stream, "download_vcodec_priority", "video_download_codec_priority")
    if stream:
        request["stream"] = stream

    output: dict[str, Any] = {}
    if include_output_paths:
        _copy_value(scope, output, "dir", "directory", skip_none=True)
        _copy_value(scope, output, "tmp_dir", "temporary_directory")
    for scope_name, request_name in (
        ("output_format", "format"),
        ("output_format_audio_only", "audio_only_format"),
        ("overwrite", "overwrite"),
        ("subpath_template", "subpath_template"),
        ("metadata_premiered_format", "metadata_format_premiered"),
    ):
        _copy_value(scope, output, scope_name, request_name)
    if output:
        request["output"] = output

    network: dict[str, Any] = {}
    for scope_name, request_name in (
        ("proxy", "proxy"),
        ("fetch_workers", "fetch_workers"),
        ("download_workers", "download_workers"),
        ("download_interval", "download_interval"),
        ("banned_mirrors_pattern", "banned_mirrors_pattern"),
    ):
        _copy_value(scope, network, scope_name, request_name)

    block_size = scope.lookup("block_size")
    if block_size is not MISSING and block_size is not None:
        network["block_size_bytes"] = int(block_size * MEBIBYTE)
    if network:
        request["network"] = network

    danmaku: dict[str, Any] = {}
    for scope_name, request_name in (
        ("danmaku_format", "format"),
        ("danmaku_font_size", "font_size"),
        ("danmaku_font", "font"),
        ("danmaku_opacity", "opacity"),
        ("danmaku_display_region_ratio", "display_region_ratio"),
        ("danmaku_speed", "speed"),
        ("danmaku_block_scroll", "block_scroll"),
        ("danmaku_block_reverse", "block_reverse"),
        ("danmaku_block_special", "block_special"),
        ("danmaku_block_colorful", "block_colorful"),
        ("danmaku_block_keyword_patterns", "block_keyword_patterns"),
    ):
        _copy_value(scope, danmaku, scope_name, request_name)

    fixed = scope.lookup("danmaku_block_fixed")
    top = scope.lookup("danmaku_block_top")
    bottom = scope.lookup("danmaku_block_bottom")
    if top is not MISSING or fixed is not MISSING:
        danmaku["block_top"] = bool(False if top is MISSING else top) or bool(False if fixed is MISSING else fixed)
    if bottom is not MISSING or fixed is not MISSING:
        danmaku["block_bottom"] = bool(False if bottom is MISSING else bottom) or bool(
            False if fixed is MISSING else fixed
        )
    if danmaku:
        request["danmaku"] = danmaku

    return request


def request_overrides_from_cli(values: Mapping[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper for callers that already have explicit CLI values."""

    return request_overrides_from_scope(Scope(values))


def request_overrides_from_settings(
    settings: YuttoConfig,
    *,
    include_output_paths: bool = True,
) -> dict[str, Any]:
    """Translate persistent settings through the same scope adapter used by the CLI."""

    return request_overrides_from_scope(
        config_scope(settings),
        include_output_paths=include_output_paths,
    )


def resolve_download_request(
    scope: Scope | Mapping[str, Any],
    settings: YuttoConfig | None = None,
    *,
    include_output_paths: bool = True,
) -> DownloadRequest:
    if not isinstance(scope, Scope):
        if settings is None:
            raise TypeError("settings are required when resolving a raw value mapping")
        scope = Scope(scope, parent=config_scope(settings))

    source = scope.lookup("source")
    if source is MISSING or source is None:
        raise ValueError("download source is missing")

    payload: dict[str, Any] = {"source": {"url": str(source)}}
    payload = _deep_merge(
        payload,
        request_overrides_from_scope(scope, include_output_paths=include_output_paths),
    )
    return DownloadRequest.model_validate(payload)


def download_request_from_mapping(payload: object, settings: YuttoConfig) -> DownloadRequest:
    """Apply explicit local settings as defaults for an RPC request payload."""

    return download_request_parser_from_settings(settings)(payload)


def download_request_parser_from_settings(settings: YuttoConfig) -> Callable[[object], DownloadRequest]:
    """Build and eagerly validate a parser for repeated server requests."""

    defaults = request_overrides_from_settings(settings, include_output_paths=False)

    def parse(payload: object) -> DownloadRequest:
        if not isinstance(payload, dict):
            return DownloadRequest.model_validate(payload)
        merged = _deep_merge(defaults, cast("dict[str, Any]", payload))
        return DownloadRequest.model_validate(merged)

    parse({"source": {"url": "yutto-server-default-validation"}})
    return parse


def _copy_value(
    scope: Scope,
    target: dict[str, Any],
    scope_name: str,
    target_name: str | None = None,
    *,
    skip_none: bool = False,
) -> None:
    value = scope.lookup(scope_name)
    if value is MISSING or (skip_none and value is None):
        return
    target[target_name or scope_name] = value


def _deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        default = merged.get(key)
        if isinstance(default, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(
                cast("dict[str, Any]", default),
                cast("dict[str, Any]", value),
            )
        else:
            merged[key] = value
    return merged


def _split_codec_pair(value: str | None, option: str) -> tuple[str, str]:
    if value is None:
        raise ValueError(f"{option} must not be null")
    codecs = value.split(":")
    if len(codecs) != 2:
        raise ValueError(f"{option} must contain exactly one ':' separator")
    return codecs[0], codecs[1]
