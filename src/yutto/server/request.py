from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from yutto.cli.settings import resolved_config_from_settings
from yutto.config import ResolvedConfig
from yutto.downloader.planner import MEBIBYTE
from yutto.stream import resolve_audio_codecs, resolve_video_codecs
from yutto.utils.time import parse_local_timestamp

if TYPE_CHECKING:
    from collections.abc import Callable

    from yutto.cli.settings import YuttoConfig


class _RpcModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceRequest(_RpcModel):
    url: str = Field(min_length=1)


class AccessRequest(_RpcModel):
    auth_profile: str | None = None
    login_strict: bool | None = None
    vip_strict: bool | None = None


class SelectionRequest(_RpcModel):
    expression: str | None = None
    skip_preview: bool | None = None
    start_time: str | None = None
    end_time: str | None = None


class ResourcesRequest(_RpcModel):
    video: bool | None = None
    audio: bool | None = None
    danmaku: bool | None = None
    subtitle: bool | None = None
    metadata: bool | None = None
    cover: bool | None = None
    chapter_info: bool | None = None
    save_cover: bool | None = None
    ai_translation_language: str | None = None


class StreamRequest(_RpcModel):
    video_quality: int | None = None
    audio_quality: int | None = None
    video_download_codec: str | None = None
    video_save_codec: str | None = None
    video_download_codec_priority: list[str] | None = None
    audio_download_codec: str | None = None
    audio_save_codec: str | None = None


class OutputRequest(_RpcModel):
    directory: str | None = None
    temporary_directory: str | None = None
    format: str | None = None
    audio_only_format: str | None = None
    overwrite: bool | None = None
    subpath_template: str | None = None
    metadata_format_premiered: str | None = None


class NetworkRequest(_RpcModel):
    proxy: str | None = None
    fetch_workers: int | None = None
    download_workers: int | None = None
    block_size_bytes: int | float | None = None
    download_interval: int | None = None
    banned_mirrors_pattern: str | None = None


class DanmakuRequest(_RpcModel):
    format: str | None = None
    font_size: int | None = None
    font: str | None = None
    opacity: int | float | None = None
    display_region_ratio: int | float | None = None
    speed: int | float | None = None
    block_top: bool | None = None
    block_bottom: bool | None = None
    block_scroll: bool | None = None
    block_reverse: bool | None = None
    block_special: bool | None = None
    block_colorful: bool | None = None
    block_keyword_patterns: list[str] | None = None


class ConfigRequest(_RpcModel):
    source: SourceRequest
    access: AccessRequest = Field(default_factory=AccessRequest)
    batch: bool | None = None
    with_extra_episodes: bool | None = None
    selection: SelectionRequest = Field(default_factory=SelectionRequest)
    resources: ResourcesRequest = Field(default_factory=ResourcesRequest)
    stream: StreamRequest = Field(default_factory=StreamRequest)
    output: OutputRequest = Field(default_factory=OutputRequest)
    network: NetworkRequest = Field(default_factory=NetworkRequest)
    danmaku: DanmakuRequest = Field(default_factory=DanmakuRequest)


def config_parser_from_settings(settings: YuttoConfig) -> Callable[[object], ResolvedConfig]:
    """Build the validated server wire-format -> flat config adapter."""
    configured_values = dict(resolved_config_from_settings(settings).values)
    configured_values.pop("output.directory", None)
    configured_values.pop("output.temporary_directory", None)
    configured = ResolvedConfig(configured_values)

    def parse(payload: object) -> ResolvedConfig:
        try:
            request = ConfigRequest.model_validate(payload)
        except ValidationError as error:
            raise ValueError(_request_validation_reason(error)) from error
        values = _config_values_from_request(request, configured)
        return configured.with_overrides(values)

    parse({"source": {"url": "yutto-server-default-validation"}})
    return parse


def _request_validation_reason(error: ValidationError) -> str:
    """Project Pydantic diagnostics into the stable server wire contract."""
    errors = error.errors(include_url=False, include_input=False)
    if errors and all(detail["type"] == "extra_forbidden" for detail in errors):
        sections: dict[str, list[str]] = {}
        for detail in errors:
            location = detail["loc"]
            field = str(location[-1])
            section = str(location[-2]) if len(location) > 1 else "request"
            sections.setdefault(section, []).append(field)
        if len(sections) == 1:
            section, fields = next(iter(sections.items()))
            return f"unknown {section} fields: {', '.join(fields)}"

    if errors:
        detail = errors[0]
        location = ".".join(str(part) for part in detail["loc"]) or "request"
        if detail["type"] == "missing":
            return f"missing required field: {location}"
        return f"invalid request field: {location}"
    return "invalid request"


def _config_values_from_request(request: ConfigRequest, baseline: ResolvedConfig) -> dict[str, Any]:
    values: dict[str, Any] = {"source.value": request.source.url}

    access = request.access
    if "auth_profile" in access.model_fields_set:
        values["auth.profile"] = "default" if access.auth_profile is None else access.auth_profile
    _copy_present_bools(
        access,
        {
            "login_strict": "auth.login_strict",
            "vip_strict": "auth.vip_strict",
        },
        values,
    )

    selection = request.selection
    _copy_present(
        selection,
        {"expression": "selection.expression"},
        values,
    )
    _copy_present_bools(
        selection,
        {"skip_preview": "selection.skip_preview"},
        values,
    )
    for field, path in {
        "start_time": "selection.published_since",
        "end_time": "selection.published_before",
    }.items():
        if field not in selection.model_fields_set:
            continue
        value = getattr(selection, field)
        values[path] = None if value is None else parse_local_timestamp(value)

    if "with_extra_episodes" in request.model_fields_set:
        values["selection.with_extra_episodes"] = bool(request.with_extra_episodes)
    if request.batch is True and "expression" not in selection.model_fields_set:
        values["selection.expression"] = "~"

    _copy_present_bools(
        request.resources,
        {
            "video": "resource.video",
            "audio": "resource.audio",
            "danmaku": "resource.danmaku",
            "subtitle": "resource.subtitle",
            "metadata": "resource.metadata",
            "cover": "resource.cover",
            "chapter_info": "resource.chapter_info",
            "save_cover": "resource.save_cover",
        },
        values,
    )
    _copy_present(
        request.resources,
        {"ai_translation_language": "resource.ai_translation_language"},
        values,
    )

    stream = request.stream
    _copy_present(
        stream,
        {
            "video_quality": "stream.video_quality",
            "audio_quality": "stream.audio_quality",
        },
        values,
    )
    if "video_download_codec_priority" in stream.model_fields_set:
        priority = stream.video_download_codec_priority
        values["stream.video_codec_priority"] = None if priority is None else tuple(priority)
    if {"video_download_codec", "video_save_codec"} & stream.model_fields_set:
        default_download, default_save = resolve_video_codecs(baseline)
        download = (
            stream.video_download_codec if "video_download_codec" in stream.model_fields_set else default_download
        )
        save = stream.video_save_codec if "video_save_codec" in stream.model_fields_set else default_save
        if download is None or save is None:
            raise ValueError("video codec fields must not be null")
        values["stream.video_codec"] = f"{download}:{save}"
    if {"audio_download_codec", "audio_save_codec"} & stream.model_fields_set:
        default_download, default_save = resolve_audio_codecs(baseline)
        download = (
            stream.audio_download_codec if "audio_download_codec" in stream.model_fields_set else default_download
        )
        save = stream.audio_save_codec if "audio_save_codec" in stream.model_fields_set else default_save
        if download is None or save is None:
            raise ValueError("audio codec fields must not be null")
        values["stream.audio_codec"] = f"{download}:{save}"

    output = request.output
    if "directory" in output.model_fields_set:
        if output.directory is None:
            raise ValueError("output.directory must not be null")
        values["output.directory"] = Path(output.directory)
    if "temporary_directory" in output.model_fields_set:
        values["output.temporary_directory"] = (
            None if output.temporary_directory is None else Path(output.temporary_directory)
        )
    _copy_present(
        output,
        {
            "format": "output.format",
            "audio_only_format": "output.audio_only_format",
            "subpath_template": "output.subpath_template",
            "metadata_format_premiered": "output.metadata_premiered_format",
        },
        values,
    )
    _copy_present_bools(output, {"overwrite": "output.overwrite"}, values)

    network = request.network
    _copy_present(
        network,
        {
            "proxy": "network.proxy",
            "fetch_workers": "network.fetch_workers",
            "download_workers": "network.download_workers",
            "download_interval": "network.download_interval",
            "banned_mirrors_pattern": "network.banned_mirrors_pattern",
        },
        values,
    )
    if "block_size_bytes" in network.model_fields_set:
        if network.block_size_bytes is None:
            raise ValueError("network.block_size_bytes must not be null")
        values["network.block_size"] = float(network.block_size_bytes) / MEBIBYTE

    danmaku = request.danmaku
    _copy_present(
        danmaku,
        {
            "format": "danmaku.format",
            "font_size": "danmaku.font_size",
            "font": "danmaku.font",
            "opacity": "danmaku.opacity",
            "display_region_ratio": "danmaku.display_region_ratio",
            "speed": "danmaku.speed",
        },
        values,
    )
    _copy_present_bools(
        danmaku,
        {
            "block_top": "danmaku.block_top",
            "block_bottom": "danmaku.block_bottom",
            "block_scroll": "danmaku.block_scroll",
            "block_reverse": "danmaku.block_reverse",
            "block_special": "danmaku.block_special",
            "block_colorful": "danmaku.block_colorful",
        },
        values,
    )
    if "block_keyword_patterns" in danmaku.model_fields_set:
        patterns = danmaku.block_keyword_patterns
        values["danmaku.block_keyword_patterns"] = None if patterns is None else tuple(patterns)

    return values


def _copy_present(model: BaseModel, paths: dict[str, str], target: dict[str, Any]) -> None:
    for field, path in paths.items():
        if field in model.model_fields_set:
            target[path] = getattr(model, field)


def _copy_present_bools(model: BaseModel, paths: dict[str, str], target: dict[str, Any]) -> None:
    for field, path in paths.items():
        if field in model.model_fields_set:
            target[path] = bool(getattr(model, field))


__all__ = ["ConfigRequest", "config_parser_from_settings"]
