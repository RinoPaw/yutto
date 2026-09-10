from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto.downloader.selector import select_audio, select_video
from yutto.utils.time import TIME_FULL_FMT

if TYPE_CHECKING:
    from pathlib import Path

    from yutto.core.options import DownloadOptions
    from yutto.resource import ResourceManifest
    from yutto.stream import AudioCodec, AudioQuality, VideoCodec, VideoQuality
    from yutto.types import AudioUrlMeta, VideoUrlMeta
    from yutto.utils.danmaku import DanmakuSaveType


@dataclass(frozen=True, slots=True)
class DownloadPaths:
    output_dir: Path
    temporary_dir: Path
    output: Path
    cover: Path
    saved_cover: Path
    chapter_info: Path


@dataclass(frozen=True, slots=True)
class VideoStream:
    index: int
    codec: VideoCodec
    width: int
    height: int
    quality: VideoQuality


@dataclass(frozen=True, slots=True)
class AudioStream:
    index: int
    codec: AudioCodec
    quality: AudioQuality


@dataclass(frozen=True, slots=True)
class DanmakuPlan:
    font_size: int | None
    font: str
    opacity: float
    display_region_ratio: float
    speed: float
    block_top: bool
    block_bottom: bool
    block_scroll: bool
    block_reverse: bool
    block_special: bool
    block_colorful: bool
    block_keyword_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MetadataPlan:
    premiered: str
    dateadded: str


@dataclass(frozen=True, slots=True)
class DownloadResources:
    """Frozen write policy derived from DownloadOptions and ResourceManifest."""

    subtitle_languages: tuple[str, ...]
    has_danmaku: bool
    danmaku_save_type: DanmakuSaveType | None
    has_metadata: bool
    has_cover: bool
    has_chapter_info: bool
    save_cover: bool
    danmaku_width: int
    danmaku_height: int
    metadata: MetadataPlan
    danmaku: DanmakuPlan


@dataclass(frozen=True, slots=True)
class DownloadPlan:
    """A side-effect-free description of one download; resource URLs stay in ResourceManifest."""

    item: str
    paths: DownloadPaths
    video: VideoStream | None
    audio: AudioStream | None
    media_requested: bool
    video_save_codec: str
    audio_save_codec: str
    attach_hvc1_tag: bool
    requires_audio_transcode_notice: bool
    overwrite: bool
    block_size: int
    banned_mirrors_pattern: str | None
    resources: DownloadResources

    @property
    def has_media(self) -> bool:
        return self.video is not None or self.audio is not None


class DownloadPlanner:
    """Turn a ResourceManifest plus a path and DownloadOptions into a pure download plan."""

    def plan(self, resources: ResourceManifest, path: Path, options: DownloadOptions) -> DownloadPlan:
        video_candidate = select_video(
            resources.videos,
            options.video_quality,
            options.video_download_codec,
            options.video_download_codec_priority,
        )
        audio_candidate = select_audio(
            resources.audios,
            options.audio_quality,
            options.audio_download_codec,
        )
        video_meta = video_candidate if options.video else None
        audio_meta = audio_candidate if options.audio else None
        suffix = resolve_output_suffix(video_meta, audio_meta, options)
        paths = resolve_paths(
            options.output_directory,
            options.temporary_directory or options.output_directory,
            path,
            suffix,
        )

        video_save_codec = options.video_save_codec
        attach_hvc1_tag = should_attach_hvc1_tag(video_meta, video_save_codec)
        if video_meta is not None and video_meta["codec"] == video_save_codec:
            video_save_codec = "copy"

        requested_audio_save_codec = options.audio_save_codec
        audio_save_codec = (
            resolve_audio_save_codec(audio_meta["codec"], requested_audio_save_codec, suffix)
            if audio_meta is not None
            else requested_audio_save_codec
        )

        selected_video_index = resources.videos.index(video_candidate) if video_candidate is not None and options.video else -1
        selected_audio_index = resources.audios.index(audio_candidate) if audio_candidate is not None and options.audio else -1
        resource_plan = DownloadResources(
            subtitle_languages=tuple(lang for lang, _ in resources.subtitles),
            has_danmaku=bool(resources.danmaku_urls),
            danmaku_save_type=resources.danmaku_save_type,
            has_metadata=options.metadata,
            has_cover=resources.cover_url is not None,
            has_chapter_info=resources.chapter_info_url is not None,
            save_cover=options.save_cover,
            danmaku_width=video_candidate["width"] if video_candidate is not None else 1920,
            danmaku_height=video_candidate["height"] if video_candidate is not None else 1080,
            metadata=MetadataPlan(
                premiered=options.metadata_format_premiered,
                dateadded=TIME_FULL_FMT,
            ),
            danmaku=DanmakuPlan(
                font_size=options.danmaku_font_size,
                font=options.danmaku_font,
                opacity=options.danmaku_opacity,
                display_region_ratio=options.danmaku_display_region_ratio,
                speed=options.danmaku_speed,
                block_top=options.danmaku_block_top,
                block_bottom=options.danmaku_block_bottom,
                block_scroll=options.danmaku_block_scroll,
                block_reverse=options.danmaku_block_reverse,
                block_special=options.danmaku_block_special,
                block_colorful=options.danmaku_block_colorful,
                block_keyword_patterns=options.danmaku_block_keyword_patterns,
            ),
        )
        return DownloadPlan(
            item=path.name,
            paths=paths,
            video=freeze_video_stream(video_meta, selected_video_index),
            audio=freeze_audio_stream(audio_meta, selected_audio_index),
            media_requested=options.video or options.audio,
            video_save_codec=video_save_codec,
            audio_save_codec=audio_save_codec,
            attach_hvc1_tag=attach_hvc1_tag,
            requires_audio_transcode_notice=(
                audio_meta is not None and audio_save_codec not in {requested_audio_save_codec, "copy"}
            ),
            overwrite=options.overwrite,
            block_size=options.block_size_bytes,
            banned_mirrors_pattern=options.banned_mirrors_pattern,
            resources=resource_plan,
        )


def resolve_paths(
    base_output_dir: Path,
    base_temporary_dir: Path,
    path: Path,
    output_suffix: str,
) -> DownloadPaths:
    output_full_path = base_output_dir / path
    output_dir, filename = output_full_path.parent, output_full_path.name
    temporary_full_path = base_temporary_dir / path
    temporary_dir, temporary_filename = temporary_full_path.parent, temporary_full_path.name
    assert filename == temporary_filename, (
        f"Filename should be the same in output and tmp dir, but got {filename} and {temporary_filename}"
    )
    return DownloadPaths(
        output_dir=output_dir,
        temporary_dir=temporary_dir,
        output=output_dir / f"{filename}{output_suffix}",
        cover=temporary_dir / f"{filename}_cover.jpg",
        saved_cover=output_dir / f"{filename}-poster.jpg",
        chapter_info=temporary_dir / f"{filename}_chapter_info.ini",
    )


def resolve_output_suffix(
    video: VideoUrlMeta | None,
    audio: AudioUrlMeta | None,
    options: DownloadOptions,
) -> str:
    if video is None:
        if options.audio_only_format != "infer":
            return f".{options.audio_only_format}"
        if audio is not None and audio["codec"] == "flac" and options.audio_save_codec in {"copy", "flac"}:
            return ".flac"
        if audio is not None and audio["codec"] == "eac3" and options.audio_save_codec in {"copy", "eac3"}:
            return ".mkv"
        return ".m4a"

    if options.output_format != "infer":
        return f".{options.output_format}"
    if audio is not None and audio["codec"] == "flac":
        return ".mkv"
    return ".mp4"


def freeze_video_stream(video: VideoUrlMeta | None, index: int) -> VideoStream | None:
    if video is None:
        return None
    return VideoStream(
        index=index,
        codec=video["codec"],
        width=video["width"],
        height=video["height"],
        quality=video["quality"],
    )


def freeze_audio_stream(audio: AudioUrlMeta | None, index: int) -> AudioStream | None:
    if audio is None:
        return None
    return AudioStream(
        index=index,
        codec=audio["codec"],
        quality=audio["quality"],
    )


def should_attach_hvc1_tag(video: VideoUrlMeta | None, video_save_codec: str) -> bool:
    """Whether the output needs the Apple-compatible hvc1 tag."""
    return (
        video is not None
        and video["quality"] != 126
        and (video_save_codec == "hevc" or (video_save_codec == "copy" and video["codec"] == "hevc"))
    )


SINGLE_CODEC_AUDIO_CONTAINERS: dict[str, tuple[frozenset[str], str]] = {
    ".mp3": (frozenset({"mp3"}), "mp3"),
    ".flac": (frozenset({"flac"}), "flac"),
    ".aac": (frozenset({"mp4a", "aac"}), "aac"),
}


def resolve_audio_save_codec(audio_codec: str, audio_save_codec: str, container_suffix: str) -> str:
    """Resolve the actual audio codec after the output container is known."""
    if audio_codec == audio_save_codec:
        return "copy"
    if audio_save_codec == "copy" and (rule := SINGLE_CODEC_AUDIO_CONTAINERS.get(container_suffix)) is not None:
        compatible_codecs, transcode_codec = rule
        if audio_codec not in compatible_codecs:
            return transcode_codec
    return audio_save_codec
