from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from yutto.selection import Selection, parse_selection
from yutto.utils.filter import PublicationTimeFilter

if TYPE_CHECKING:
    from pathlib import Path

    from yutto.core.request import DownloadRequest
    from yutto.listing import PathOptions
    from yutto.stream import AudioCodec, AudioQuality, VideoCodec, VideoQuality


@dataclass(frozen=True, slots=True, kw_only=True)
class AccessOptions:
    login_strict: bool = False
    vip_strict: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionOptions:
    auth_profile: str = "default"
    proxy: str = "auto"
    fetch_workers: int = 8
    download_workers: int = 8


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceOptions:
    selection: Selection | None = None
    with_extra_episodes: bool = False
    skip_preview: bool = False
    fetch_tags: bool = False
    publication_time_filter: PublicationTimeFilter | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceOptions:
    video: bool = True
    audio: bool = True
    danmaku: bool = True
    subtitle: bool = True
    cover: bool = True
    chapter_info: bool = True
    ai_translation_language: str | None = None
    danmaku_format: Literal["xml", "ass", "protobuf"] = "ass"


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadOptions:
    video: bool
    audio: bool
    metadata: bool
    save_cover: bool
    video_quality: VideoQuality
    audio_quality: AudioQuality
    video_download_codec: VideoCodec
    video_save_codec: str
    video_download_codec_priority: tuple[VideoCodec, ...] | None
    audio_download_codec: AudioCodec
    audio_save_codec: str
    output_directory: Path
    temporary_directory: Path | None
    output_format: Literal["infer", "mp4", "mkv", "mov"]
    audio_only_format: Literal["infer", "m4a", "aac", "mp3", "flac", "mp4", "mkv", "mov"]
    overwrite: bool
    metadata_format_premiered: str
    enforce_directory_boundary: bool
    download_interval: int
    block_size_bytes: int
    banned_mirrors_pattern: str | None
    danmaku_font_size: int | None
    danmaku_font: str
    danmaku_opacity: float
    danmaku_display_region_ratio: float
    danmaku_speed: float
    danmaku_block_top: bool
    danmaku_block_bottom: bool
    danmaku_block_scroll: bool
    danmaku_block_reverse: bool
    danmaku_block_special: bool
    danmaku_block_colorful: bool
    danmaku_block_keyword_patterns: tuple[str, ...]


DEFAULT_ACCESS_OPTIONS = AccessOptions()
DEFAULT_EXECUTION_OPTIONS = ExecutionOptions()
DEFAULT_SOURCE_OPTIONS = SourceOptions()
DEFAULT_RESOURCE_OPTIONS = ResourceOptions()


def access_options_from_request(request: DownloadRequest) -> AccessOptions:
    return AccessOptions(
        login_strict=request.access.login_strict,
        vip_strict=request.access.vip_strict,
    )


def execution_options_from_request(request: DownloadRequest) -> ExecutionOptions:
    return ExecutionOptions(
        auth_profile=request.access.auth_profile,
        proxy=request.network.proxy,
        fetch_workers=request.network.fetch_workers,
        download_workers=request.network.download_workers,
    )


def source_options_from_request(request: DownloadRequest) -> SourceOptions:
    expression = request.selection.expression
    publication_time_filter = None
    if request.selection.start_time is not None or request.selection.end_time is not None:
        publication_time_filter = PublicationTimeFilter.from_strings(
            request.selection.start_time,
            request.selection.end_time,
        )
    return SourceOptions(
        selection=parse_selection(expression) if expression is not None else None,
        with_extra_episodes=request.scope.with_extra_episodes,
        skip_preview=request.selection.skip_preview,
        fetch_tags=request.resources.metadata,
        publication_time_filter=publication_time_filter,
    )


def path_options_from_request(request: DownloadRequest) -> PathOptions:
    from yutto.listing import PathOptions

    return PathOptions(subpath_template=request.output.subpath_template)


def resource_options_from_request(request: DownloadRequest) -> ResourceOptions:
    resources = request.resources
    return ResourceOptions(
        video=resources.video,
        audio=resources.audio,
        danmaku=resources.danmaku,
        subtitle=resources.subtitle,
        cover=resources.cover,
        chapter_info=resources.chapter_info,
        ai_translation_language=resources.ai_translation_language,
        danmaku_format=request.danmaku.format,
    )


def download_options_from_request(request: DownloadRequest) -> DownloadOptions:
    resources = request.resources
    stream = request.stream
    output = request.output
    network = request.network
    danmaku = request.danmaku
    return DownloadOptions(
        video=resources.video,
        audio=resources.audio,
        metadata=resources.metadata,
        save_cover=resources.save_cover,
        video_quality=stream.video_quality,
        audio_quality=stream.audio_quality,
        video_download_codec=stream.video_download_codec,
        video_save_codec=stream.video_save_codec,
        video_download_codec_priority=(
            tuple(stream.video_download_codec_priority) if stream.video_download_codec_priority is not None else None
        ),
        audio_download_codec=stream.audio_download_codec,
        audio_save_codec=stream.audio_save_codec,
        output_directory=output.directory,
        temporary_directory=output.temporary_directory,
        output_format=output.format,
        audio_only_format=output.audio_only_format,
        overwrite=output.overwrite,
        metadata_format_premiered=output.metadata_format_premiered,
        enforce_directory_boundary=output.enforce_directory_boundary,
        download_interval=network.download_interval,
        block_size_bytes=network.block_size_bytes,
        banned_mirrors_pattern=network.banned_mirrors_pattern,
        danmaku_font_size=danmaku.font_size,
        danmaku_font=danmaku.font,
        danmaku_opacity=danmaku.opacity,
        danmaku_display_region_ratio=danmaku.display_region_ratio,
        danmaku_speed=danmaku.speed,
        danmaku_block_top=danmaku.block_top,
        danmaku_block_bottom=danmaku.block_bottom,
        danmaku_block_scroll=danmaku.block_scroll,
        danmaku_block_reverse=danmaku.block_reverse,
        danmaku_block_special=danmaku.block_special,
        danmaku_block_colorful=danmaku.block_colorful,
        danmaku_block_keyword_patterns=tuple(danmaku.block_keyword_patterns),
    )


__all__ = [
    "DEFAULT_ACCESS_OPTIONS",
    "DEFAULT_EXECUTION_OPTIONS",
    "DEFAULT_RESOURCE_OPTIONS",
    "DEFAULT_SOURCE_OPTIONS",
    "AccessOptions",
    "DownloadOptions",
    "ExecutionOptions",
    "ResourceOptions",
    "SourceOptions",
    "access_options_from_request",
    "download_options_from_request",
    "execution_options_from_request",
    "path_options_from_request",
    "resource_options_from_request",
    "source_options_from_request",
]
