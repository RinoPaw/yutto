from __future__ import annotations

from typing import TYPE_CHECKING, cast

from yutto.cli.settings import scope_from_config
from yutto.core.request import DownloadRequest
from yutto.scope import MISSING, Scope

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
    """Translate resolved Scope specs into the temporary DownloadRequest model."""

    request: dict[str, Any] = {}

    access: dict[str, Any] = {}
    _copy_value(scope.auth.profile, access, "auth_profile")
    _copy_value(scope.auth.login_strict, access, "login_strict")
    _copy_value(scope.auth.vip_strict, access, "vip_strict")
    if access:
        request["access"] = access

    selection: dict[str, Any] = {}
    _copy_value(scope.selection.expression, selection, "expression")
    _copy_value(scope.selection.skip_preview, selection, "skip_preview")
    _copy_value(scope.selection.published_since, selection, "start_time")
    _copy_value(scope.selection.published_before, selection, "end_time")
    if selection:
        request["selection"] = selection

    _copy_value(scope.selection.with_extra_episodes, request, "with_extra_episodes")

    resources: dict[str, Any] = {}
    _copy_value(scope.resource.video, resources, "video")
    _copy_value(scope.resource.audio, resources, "audio")
    _copy_value(scope.resource.danmaku, resources, "danmaku")
    _copy_value(scope.resource.subtitle, resources, "subtitle")
    _copy_value(scope.resource.metadata, resources, "metadata")
    _copy_value(scope.resource.cover, resources, "cover")
    _copy_value(scope.resource.chapter_info, resources, "chapter_info")
    _copy_value(scope.resource.save_cover, resources, "save_cover")
    _copy_value(scope.resource.ai_translation_language, resources, "ai_translation_language")
    if resources:
        request["resources"] = resources

    stream: dict[str, Any] = {}
    _copy_value(scope.stream.video_quality, stream, "video_quality")
    _copy_value(scope.stream.audio_quality, stream, "audio_quality")

    video_codec = scope.stream.video_codec
    if video_codec is not MISSING:
        stream["video_download_codec"], stream["video_save_codec"] = _split_codec_pair(video_codec, "vcodec")

    audio_codec = scope.stream.audio_codec
    if audio_codec is not MISSING:
        stream["audio_download_codec"], stream["audio_save_codec"] = _split_codec_pair(audio_codec, "acodec")

    _copy_value(scope.stream.video_codec_priority, stream, "video_download_codec_priority")
    if stream:
        request["stream"] = stream

    output: dict[str, Any] = {}
    if include_output_paths:
        _copy_value(scope.output.directory, output, "directory", skip_none=True)
        _copy_value(scope.output.temporary_directory, output, "temporary_directory")
    _copy_value(scope.output.format, output, "format")
    _copy_value(scope.output.audio_only_format, output, "audio_only_format")
    _copy_value(scope.output.overwrite, output, "overwrite")
    _copy_value(scope.output.subpath_template, output, "subpath_template")
    _copy_value(scope.output.metadata_premiered_format, output, "metadata_format_premiered")
    if output:
        request["output"] = output

    network: dict[str, Any] = {}
    _copy_value(scope.network.proxy, network, "proxy")
    _copy_value(scope.network.fetch_workers, network, "fetch_workers")
    _copy_value(scope.network.download_workers, network, "download_workers")
    _copy_value(scope.network.download_interval, network, "download_interval")
    _copy_value(scope.network.banned_mirrors_pattern, network, "banned_mirrors_pattern")

    block_size = scope.network.block_size
    if block_size is not MISSING and block_size is not None:
        network["block_size_bytes"] = int(block_size * MEBIBYTE)
    if network:
        request["network"] = network

    danmaku: dict[str, Any] = {}
    _copy_value(scope.danmaku.format, danmaku, "format")
    _copy_value(scope.danmaku.font_size, danmaku, "font_size")
    _copy_value(scope.danmaku.font, danmaku, "font")
    _copy_value(scope.danmaku.opacity, danmaku, "opacity")
    _copy_value(scope.danmaku.display_region_ratio, danmaku, "display_region_ratio")
    _copy_value(scope.danmaku.speed, danmaku, "speed")
    _copy_value(scope.danmaku.block_scroll, danmaku, "block_scroll")
    _copy_value(scope.danmaku.block_reverse, danmaku, "block_reverse")
    _copy_value(scope.danmaku.block_special, danmaku, "block_special")
    _copy_value(scope.danmaku.block_colorful, danmaku, "block_colorful")
    _copy_value(scope.danmaku.block_keyword_patterns, danmaku, "block_keyword_patterns")

    fixed = scope.danmaku.block_fixed
    top = scope.danmaku.block_top
    bottom = scope.danmaku.block_bottom
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
    """Translate a mapping that already uses canonical Scope paths."""
    return request_overrides_from_scope(Scope(values))


def request_overrides_from_settings(
    settings: YuttoConfig,
    *,
    include_output_paths: bool = True,
) -> dict[str, Any]:
    """Translate persistent settings through the same Scope adapter used by the CLI."""

    return request_overrides_from_scope(
        scope_from_config(settings),
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
        scope = Scope(scope, parent=scope_from_config(settings))

    source = scope.source.value
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
    value: Any,
    target: dict[str, Any],
    target_name: str,
    *,
    skip_none: bool = False,
) -> None:
    if value is MISSING or (skip_none and value is None):
        return
    target[target_name] = value


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


def _split_codec_pair(value: str | None | object, option: str) -> tuple[str, str]:
    if value is None:
        raise ValueError(f"{option} must not be null")
    if not isinstance(value, str):
        raise TypeError(f"{option} must be a string")
    codecs = value.split(":")
    if len(codecs) != 2:
        raise ValueError(f"{option} must contain exactly one ':' separator")
    return codecs[0], codecs[1]
