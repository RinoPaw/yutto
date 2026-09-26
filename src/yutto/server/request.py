from __future__ import annotations

from dataclasses import replace
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


# Sparse RPC models use None only as the internal default for omitted fields.
# Non-nullable annotations reject an explicit JSON null; model_fields_set keeps
# omission distinct from a supplied value.
_OMITTED: Any = None


class _RpcModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=False)


class SourceRequest(_RpcModel):
    url: str = Field(min_length=1)


class AccessRequest(_RpcModel):
    auth_profile: str = _OMITTED
    login_strict: bool = _OMITTED
    vip_strict: bool = _OMITTED


class SelectionRequest(_RpcModel):
    expression: str | None = None
    skip_preview: bool = _OMITTED
    start_time: str | None = None
    end_time: str | None = None


class ResourcesRequest(_RpcModel):
    video: bool = _OMITTED
    audio: bool = _OMITTED
    danmaku: bool = _OMITTED
    subtitle: bool = _OMITTED
    metadata: bool = _OMITTED
    cover: bool = _OMITTED
    chapter_info: bool = _OMITTED
    save_cover: bool = _OMITTED
    ai_translation_language: str | None = None


class StreamRequest(_RpcModel):
    video_quality: int = _OMITTED
    audio_quality: int = _OMITTED
    video_download_codec: str = _OMITTED
    video_save_codec: str = _OMITTED
    video_download_codec_priority: list[str] | None = None
    audio_download_codec: str = _OMITTED
    audio_save_codec: str = _OMITTED


class OutputRequest(_RpcModel):
    directory: str = _OMITTED
    temporary_directory: str | None = None
    format: str = _OMITTED
    audio_only_format: str = _OMITTED
    overwrite: bool = _OMITTED
    subpath_template: str = _OMITTED
    metadata_format_premiered: str = _OMITTED


class NetworkRequest(_RpcModel):
    proxy: str = _OMITTED
    fetch_workers: int = _OMITTED
    download_workers: int = _OMITTED
    block_size_bytes: int | float = _OMITTED
    download_interval: int = _OMITTED
    banned_mirrors_pattern: str | None = None


class DanmakuRequest(_RpcModel):
    format: str = _OMITTED
    font_size: int | None = None
    font: str = _OMITTED
    opacity: int | float = _OMITTED
    display_region_ratio: int | float = _OMITTED
    speed: int | float = _OMITTED
    block_top: bool = _OMITTED
    block_bottom: bool = _OMITTED
    block_scroll: bool = _OMITTED
    block_reverse: bool = _OMITTED
    block_special: bool = _OMITTED
    block_colorful: bool = _OMITTED
    block_keyword_patterns: list[str] | None = None


class ConfigRequest(_RpcModel):
    source: SourceRequest
    access: AccessRequest = Field(default_factory=AccessRequest)
    batch: bool = _OMITTED
    with_extra_episodes: bool = _OMITTED
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
        credential = replace(credential, profile=access_request.auth_profile)
    if "login_strict" in access_request.model_fields_set:
        access = replace(access, login_strict=access_request.login_strict)
    if "vip_strict" in access_request.model_fields_set:
        access = replace(access, vip_strict=access_request.vip_strict)

    selection_request = request.selection
    selection_updates: dict[str, object] = {}
    if "expression" in selection_request.model_fields_set:
        selection_updates["expression"] = selection_request.expression
    if "skip_preview" in selection_request.model_fields_set:
        selection_updates["skip_preview"] = selection_request.skip_preview
    if "start_time" in selection_request.model_fields_set:
        value = selection_request.start_time
        selection_updates["published_since"] = None if value is None else parse_local_timestamp(value)
    if "end_time" in selection_request.model_fields_set:
        value = selection_request.end_time
        selection_updates["published_before"] = None if value is None else parse_local_timestamp(value)
    if "with_extra_episodes" in request.model_fields_set:
        selection_updates["with_extra_episodes"] = request.with_extra_episodes
    if request.batch is True and "expression" not in selection_request.model_fields_set:
        selection_updates["expression"] = "~"
    selection = replace(baseline.selection, **selection_updates)

    resource = replace(
        baseline.resource,
        **_present_updates(
            request.resources,
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
        ),
    )

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
        stream_updates["video_codec"] = f"{download}:{save}"
    if {"audio_download_codec", "audio_save_codec"} & stream_request.model_fields_set:
        default_download, default_save = resolve_audio_codecs(baseline)
        download = (
            stream_request.audio_download_codec
            if "audio_download_codec" in stream_request.model_fields_set
            else default_download
        )
        save = stream_request.audio_save_codec if "audio_save_codec" in stream_request.model_fields_set else default_save
        stream_updates["audio_codec"] = f"{download}:{save}"
    stream = replace(baseline.stream, **stream_updates)

    output_request = request.output
    output_updates = _present_updates(
        output_request,
        {
            "format": "format",
            "audio_only_format": "audio_only_format",
            "overwrite": "overwrite",
            "subpath_template": "subpath_template",
            "metadata_format_premiered": "metadata_premiered_format",
        },
    )
    if "directory" in output_request.model_fields_set:
        output_updates["directory"] = Path(output_request.directory)
    if "temporary_directory" in output_request.model_fields_set:
        temporary_directory = output_request.temporary_directory
        output_updates["temporary_directory"] = None if temporary_directory is None else Path(temporary_directory)
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
            "block_top": "block_top",
            "block_bottom": "block_bottom",
            "block_scroll": "block_scroll",
            "block_reverse": "block_reverse",
            "block_special": "block_special",
            "block_colorful": "block_colorful",
        },
    )
    for field in ("opacity", "display_region_ratio", "speed"):
        if field in danmaku_updates:
            danmaku_updates[field] = float(danmaku_updates[field])
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
