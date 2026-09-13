from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from yutto.core.request import DownloadRequest

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Mapping
    from typing import Any

    from yutto.cli.settings import YuttoSettings

MEBIBYTE = 1024 * 1024


def request_overrides_from_namespace(args: argparse.Namespace) -> dict[str, Any]:
    """Translate only explicitly supplied download CLI options into a request patch."""
    values = vars(args)
    request: dict[str, Any] = {}

    access: dict[str, Any] = {}
    if "auth_profile" in values:
        access["auth_profile"] = values["auth_profile"]
    if "login_strict" in values:
        access["login_strict"] = values["login_strict"]
    if "vip_strict" in values:
        access["vip_strict"] = values["vip_strict"]
    if access:
        request["access"] = access

    selection: dict[str, Any] = {}
    if "selection_expr" in values:
        selection["expression"] = values["selection_expr"]
    elif values.get("batch"):
        selection["expression"] = "~"
    if "skip_preview" in values:
        selection["skip_preview"] = values["skip_preview"]
    if "publication_start_time" in values:
        selection["start_time"] = values["publication_start_time"]
    if "publication_end_time" in values:
        selection["end_time"] = values["publication_end_time"]
    if selection:
        request["selection"] = selection

    if "with_extra_episodes" in values:
        request["with_extra_episodes"] = values["with_extra_episodes"]

    resources: dict[str, Any] = {}
    for cli_name, request_name in (
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
        if cli_name in values:
            resources[request_name] = values[cli_name]
    if resources:
        request["resources"] = resources

    stream: dict[str, Any] = {}
    if "video_quality" in values:
        stream["video_quality"] = values["video_quality"]
    if "audio_quality" in values:
        stream["audio_quality"] = values["audio_quality"]
    if "vcodec" in values:
        stream["video_download_codec"], stream["video_save_codec"] = _split_codec_pair(values["vcodec"], "vcodec")
    if "acodec" in values:
        stream["audio_download_codec"], stream["audio_save_codec"] = _split_codec_pair(values["acodec"], "acodec")
    if "download_vcodec_priority" in values:
        stream["video_download_codec_priority"] = values["download_vcodec_priority"]
    if stream:
        request["stream"] = stream

    output: dict[str, Any] = {}
    for cli_name, request_name in (
        ("dir", "directory"),
        ("tmp_dir", "temporary_directory"),
        ("output_format", "format"),
        ("output_format_audio_only", "audio_only_format"),
        ("overwrite", "overwrite"),
        ("subpath_template", "subpath_template"),
        ("metadata_premiered_format", "metadata_format_premiered"),
    ):
        if cli_name in values:
            output[request_name] = values[cli_name]
    if output:
        request["output"] = output

    network: dict[str, Any] = {}
    for cli_name, request_name in (
        ("proxy", "proxy"),
        ("fetch_workers", "fetch_workers"),
        ("download_workers", "download_workers"),
        ("download_interval", "download_interval"),
        ("banned_mirrors_pattern", "banned_mirrors_pattern"),
    ):
        if cli_name in values:
            network[request_name] = values[cli_name]
    if "block_size" in values:
        network["block_size_bytes"] = int(values["block_size"] * MEBIBYTE)
    if network:
        request["network"] = network

    danmaku: dict[str, Any] = {}
    for cli_name, request_name in (
        ("danmaku_format", "format"),
        ("danmaku_font_size", "font_size"),
        ("danmaku_font", "font"),
        ("danmaku_opacity", "opacity"),
        ("danmaku_display_region_ratio", "display_region_ratio"),
        ("danmaku_speed", "speed"),
        ("danmaku_block_top", "block_top"),
        ("danmaku_block_bottom", "block_bottom"),
        ("danmaku_block_scroll", "block_scroll"),
        ("danmaku_block_reverse", "block_reverse"),
        ("danmaku_block_special", "block_special"),
        ("danmaku_block_colorful", "block_colorful"),
        ("danmaku_block_keyword_patterns", "block_keyword_patterns"),
    ):
        if cli_name in values:
            danmaku[request_name] = values[cli_name]
    if values.get("danmaku_block_fixed"):
        danmaku["block_top"] = True
        danmaku["block_bottom"] = True
    if danmaku:
        request["danmaku"] = danmaku

    return request


def request_overrides_from_settings(
    settings: YuttoSettings,
    *,
    include_output_paths: bool = True,
) -> dict[str, Any]:
    """Translate explicitly configured TOML fields into a frontend-independent request patch."""
    request: dict[str, Any] = {}

    basic = settings.basic
    basic_set = basic.model_fields_set

    access: dict[str, Any] = {}
    if "login_strict" in basic_set:
        access["login_strict"] = basic.login_strict
    if "vip_strict" in basic_set:
        access["vip_strict"] = basic.vip_strict
    if "auth_profile" in settings.auth.model_fields_set:
        access["auth_profile"] = settings.auth.auth_profile
    if access:
        request["access"] = access

    batch_set = settings.batch.model_fields_set
    selection: dict[str, Any] = {}
    if "skip_preview" in batch_set:
        selection["skip_preview"] = settings.batch.skip_preview
    if "batch_filter_start_time" in batch_set:
        selection["start_time"] = settings.batch.batch_filter_start_time
    if "batch_filter_end_time" in batch_set:
        selection["end_time"] = settings.batch.batch_filter_end_time
    if selection:
        request["selection"] = selection
    if "with_extra_episodes" in batch_set:
        request["with_extra_episodes"] = settings.batch.with_extra_episodes

    resource = settings.resource
    resource_set = resource.model_fields_set
    resources: dict[str, Any] = {}
    for settings_name, request_name in (
        ("require_video", "video"),
        ("require_audio", "audio"),
        ("require_danmaku", "danmaku"),
        ("require_subtitle", "subtitle"),
        ("require_metadata", "metadata"),
        ("require_cover", "cover"),
        ("require_chapter_info", "chapter_info"),
        ("save_cover", "save_cover"),
    ):
        if settings_name in resource_set:
            resources[request_name] = getattr(resource, settings_name)
    if "ai_translation_language" in basic_set:
        resources["ai_translation_language"] = basic.ai_translation_language
    if resources:
        request["resources"] = resources

    stream: dict[str, Any] = {}
    if "video_quality" in basic_set:
        stream["video_quality"] = basic.video_quality
    if "audio_quality" in basic_set:
        stream["audio_quality"] = basic.audio_quality
    if "vcodec" in basic_set:
        stream["video_download_codec"], stream["video_save_codec"] = _split_codec_pair(basic.vcodec, "vcodec")
    if "acodec" in basic_set:
        stream["audio_download_codec"], stream["audio_save_codec"] = _split_codec_pair(basic.acodec, "acodec")
    if "download_vcodec_priority" in basic_set:
        stream["video_download_codec_priority"] = basic.download_vcodec_priority
    if stream:
        request["stream"] = stream

    output: dict[str, Any] = {}
    if include_output_paths and "dir" in basic_set:
        output["directory"] = Path(basic.dir).expanduser()
    if include_output_paths and "tmp_dir" in basic_set:
        output["temporary_directory"] = None if basic.tmp_dir is None else Path(basic.tmp_dir).expanduser()
    for settings_name, request_name in (
        ("output_format", "format"),
        ("output_format_audio_only", "audio_only_format"),
        ("overwrite", "overwrite"),
        ("subpath_template", "subpath_template"),
        ("metadata_format_premiered", "metadata_format_premiered"),
    ):
        if settings_name in basic_set:
            output[request_name] = getattr(basic, settings_name)
    if output:
        request["output"] = output

    network: dict[str, Any] = {}
    for settings_name, request_name in (
        ("proxy", "proxy"),
        ("fetch_workers", "fetch_workers"),
        ("num_workers", "download_workers"),
        ("download_interval", "download_interval"),
        ("banned_mirrors_pattern", "banned_mirrors_pattern"),
    ):
        if settings_name in basic_set:
            network[request_name] = getattr(basic, settings_name)
    if "block_size" in basic_set:
        network["block_size_bytes"] = int(basic.block_size * MEBIBYTE)
    if network:
        request["network"] = network

    danmaku_settings = settings.danmaku
    danmaku_set = danmaku_settings.model_fields_set
    danmaku: dict[str, Any] = {}
    if "danmaku_format" in basic_set:
        danmaku["format"] = basic.danmaku_format
    for settings_name, request_name in (
        ("font_size", "font_size"),
        ("font", "font"),
        ("opacity", "opacity"),
        ("display_region_ratio", "display_region_ratio"),
        ("speed", "speed"),
        ("block_scroll", "block_scroll"),
        ("block_reverse", "block_reverse"),
        ("block_special", "block_special"),
        ("block_colorful", "block_colorful"),
        ("block_keyword_patterns", "block_keyword_patterns"),
    ):
        if settings_name in danmaku_set:
            danmaku[request_name] = getattr(danmaku_settings, settings_name)
    if {"block_top", "block_fixed"} & danmaku_set:
        danmaku["block_top"] = danmaku_settings.block_top or danmaku_settings.block_fixed
    if {"block_bottom", "block_fixed"} & danmaku_set:
        danmaku["block_bottom"] = danmaku_settings.block_bottom or danmaku_settings.block_fixed
    if danmaku:
        request["danmaku"] = danmaku

    return request


def resolve_download_request(
    source: str,
    settings: YuttoSettings,
    cli_overrides: Mapping[str, Any] | None = None,
    *,
    include_output_paths: bool = True,
) -> DownloadRequest:
    payload: dict[str, Any] = {"source": {"url": source}}
    payload = _deep_merge(
        payload,
        request_overrides_from_settings(settings, include_output_paths=include_output_paths),
    )
    if cli_overrides:
        payload = _deep_merge(payload, cast("dict[str, Any]", dict(cli_overrides)))
    return DownloadRequest.model_validate(payload)


def download_request_from_mapping(payload: object, settings: YuttoSettings) -> DownloadRequest:
    """Apply explicit local settings as defaults for an RPC request payload."""
    return download_request_parser_from_settings(settings)(payload)


def download_request_parser_from_settings(settings: YuttoSettings) -> Callable[[object], DownloadRequest]:
    """Build and eagerly validate a parser for repeated server requests."""
    defaults = request_overrides_from_settings(settings, include_output_paths=False)

    def parse(payload: object) -> DownloadRequest:
        if not isinstance(payload, dict):
            return DownloadRequest.model_validate(payload)
        merged = _deep_merge(defaults, cast("dict[str, Any]", payload))
        return DownloadRequest.model_validate(merged)

    parse({"source": {"url": "yutto-server-default-validation"}})
    return parse


def download_request_from_namespace(args: argparse.Namespace) -> DownloadRequest:
    """Compatibility adapter for callers that still hold an argparse namespace."""
    from yutto.cli.settings import YuttoSettings

    settings = getattr(args, "_settings", YuttoSettings())
    source = getattr(args, "source", getattr(args, "url", None))
    if source is None:
        raise ValueError("download source is missing")
    overrides = getattr(args, "_request_overrides", None)
    if overrides is None:
        overrides = request_overrides_from_namespace(args)
    return resolve_download_request(source, settings, overrides)


def merge_request_patches(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    return _deep_merge(cast("dict[str, Any]", dict(base)), cast("dict[str, Any]", dict(overrides)))


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


def _split_codec_pair(value: str, option: str) -> tuple[str, str]:
    codecs = value.split(":")
    if len(codecs) != 2:
        raise ValueError(f"{option} must contain exactly one ':' separator")
    return codecs[0], codecs[1]
