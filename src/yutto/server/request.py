from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

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
    """Build the validated server wire-format -> typed task config adapter."""
    configured = resolved_config_from_settings(settings)
    configured = replace(
        configured,
        output=replace(
            configured.output,
            directory=Path(),
            temporary_directory=None,
        ),
    )

    def parse(payload: object) -> ResolvedConfig:
        try:
            request = ConfigRequest.model_validate(payload)
        except ValidationError as error:
            raise ValueError(_request_validation_reason(error)) from error
        return _config_from_request(request, configured)

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


def _config_from_request(request: ConfigRequest, baseline: ResolvedConfig) -> ResolvedConfig:
    source = replace(baseline.source, value=request.source.url)

    credential = baseline.credential
    access = baseline.access
    access_request = request.access
    if "auth_profile" in access_request.model_fields_set:
        credential = replace(
            credential,
            profile="default" if access_request.auth_profile is None else access_request.auth_profile,
        )
    if "login_strict" in access_request.model_fields_set:
        access = replace(access, login_strict=bool(access_request.login_strict))
    if "vip_strict" in access_request.model_fields_set:
        access = replace(access, vip_strict=bool(access_request.vip_strict))

    selection = baseline.selection
    selection_request = request.selection
    selection_updates: dict[str, object] = {}
    if "expression" in selection_request.model_fields_set:
        selection_updates["expression"] = selection_request.expression
    if "skip_preview" in selection_request.model_fields_set:
        selection_updates["skip_preview"] = bool(selection_request.skip_preview)
    if "start_time" in selection_request.model_fields_set:
        value = selection_request.start_time
        selection_updates["published_since"] = None if value is None else parse_local_timestamp(value)
    if "end_time" in selection_request.model_fields_set:
        value = selection_request.end_time
        selection_updates["published_before"] = None if value is None else parse_local_timestamp(value)
    if "with_extra_episodes" in request.model_fields_set:
        selection_updates["with_extra_episodes"] = bool(request.with_extra_episodes)
    if request.batch is True and "expression" not in selection_request.model_fields_set:
        selection_updates["expression"] = "~"
    selection = replace(selection, **selection_updates)

    resources = request.resources
    resource_updates = _present_updates(
        resources,
        {
            "video": "video",
            "audio": "audio",
            "danmaku": "danmaku",
            "subtitle": "subtitle",
            "metadata": "metadata",
            "cover": "cover",
            "chapter_info": "chapter_info",
            "save_cover": "save_cover",
            "ai_translation_language": "ai_translation_language",
        },
    )
    for field in (
        "video",
        "audio",
        "danmaku",
        "subtitle",
        "metadata",
        "cover",
        "chapter_info",
        "save_cover",
    ):
        if field in resource_updates:
            resource_updates[field] = bool(resource_updates[field])
    resource = replace(baseline.resource, **resource_updates)

    stream_request = request.stream
    stream_updates = _present_updates(
        stream_request,
        {
            "video_quality": "video_quality",
            "audio_quality": "audio_quality",
        },
    )
    if "video_download_codec_priority" in stream_request.model_fields_set:
        priority = stream_request.video_download_codec_priority
        stream_updates["video_codec_priority"] = None if priority is None else tuple(priority)
    if {"video_download_codec", "video_save_codec"} & stream_request.model_fields_set:
        default_download, default_save = resolve_video_codecs(baseline)
        download = (
            stream_request.video_download_codec
            if "video_download_codec" in stream_request.model_fields_set
            else default_download
        )
        save = stream_request.video_save_codec if "video_save_codec" in stream_request.model_fields_set else default_save
        if download is None or save is None:
            raise ValueError("video codec fields must not be null")
        stream_updates["video_codec"] = f"{download}:{save}"
    if {"audio_download_codec", "audio_save_codec"} & stream_request.model_fields_set:
        default_download, default_save = resolve_audio_codecs(baseline)
        download = (
            stream_request.audio_download_codec
            if "audio_download_codec" in stream_request.model_fields_set
            else default_download
        )
        save = stream_request.audio_save_codec if "audio_save_codec" in stream_request.model_fields_set else default_save
        if download is None or save is None:
            raise ValueError("audio codec fields must not be null")
        stream_updates["audio_codec"] = f"{download}:{save}"
    stream = replace(baseline.stream, **stream_updates)

    output_request = request.output
    output_updates = _present_updates(
        output_request,
        {
            "format": "format",
            "audio_only_format": "audio_only_format",
            "subpath_template": "subpath_template",
            "metadata_format_premiered": "metadata_premiered_format",
        },
    )
    if "directory" in output_request.model_fields_set:
        if output_request.directory is None:
            raise ValueError("output.directory must not be null")
        output_updates["directory"] = Path(output_request.directory)
    if "temporary_directory" in output_request.model_fields_set:
        output_updates["temporary_directory"] = (
            None if output_request.temporary_directory is None else Path(output_request.temporary_directory)
        )
    if "overwrite" in output_request.model_fields_set:
        output_updates["overwrite"] = bool(output_request.overwrite)
    output = replace(baseline.output, **output_updates)

    network_request = request.network
    network_updates = _present_updates(
        network_request,
        {
            "proxy": "proxy",
            "fetch_workers": "fetch_workers",
            "download_workers": "download_workers",
            "download_interval": "download_interval",
            "banned_mirrors_pattern": "banned_mirrors_pattern",
        },
    )
    if "block_size_bytes" in network_request.model_fields_set:
        if network_request.block_size_bytes is None:
            raise ValueError("network.block_size_bytes must not be null")
        network_updates["block_size"] = float(network_request.block_size_bytes) / MEBIBYTE
    network = replace(baseline.network, **network_updates)

    danmaku_request = request.danmaku
    danmaku_updates = _present_updates(
        danmaku_request,
        {
            "format": "format",
            "font_size": "font_size",
            "font": "font",
            "opacity": "opacity",
            "display_region_ratio": "display_region_ratio",
            "speed": "speed",
        },
    )
    for field in ("opacity", "display_region_ratio", "speed"):
        if field in danmaku_updates and danmaku_updates[field] is not None:
            danmaku_updates[field] = float(danmaku_updates[field])
    for field in (
        "block_top",
        "block_bottom",
        "block_scroll",
        "block_reverse",
        "block_special",
        "block_colorful",
    ):
        if field in danmaku_request.model_fields_set:
            danmaku_updates[field] = bool(getattr(danmaku_request, field))
    if "block_keyword_patterns" in danmaku_request.model_fields_set:
        patterns = danmaku_request.block_keyword_patterns
        danmaku_updates["block_keyword_patterns"] = None if patterns is None else tuple(patterns)
    danmaku = replace(baseline.danmaku, **danmaku_updates)

    return replace(
        baseline,
        source=source,
        credential=credential,
        access=access,
        selection=selection,
        resource=resource,
        stream=stream,
        output=output,
        network=network,
        danmaku=danmaku,
    )


def _present_updates(model: BaseModel, fields: dict[str, str]) -> dict[str, object]:
    return {
        target: getattr(model, source)
        for source, target in fields.items()
        if source in model.model_fields_set
    }


__all__ = ["ConfigRequest", "config_parser_from_settings"]
