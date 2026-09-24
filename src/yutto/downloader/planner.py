from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from yutto.downloader.selector import select_streams
from yutto.output_formats import resolve_audio_only_output_format, resolve_output_format
from yutto.resource import resolve_danmaku_format, should_save_cover, wants_metadata
from yutto.stream import resolve_audio_codecs, resolve_video_codecs
from yutto.utils.time import TIME_FULL_FMT

if TYPE_CHECKING:
    from yutto.resource import ResourceManifest
    from yutto.scope import Scope
    from yutto.stream import AudioCodec, AudioQuality, VideoCodec, VideoQuality
    from yutto.types import AudioUrlMeta, VideoUrlMeta
    from yutto.utils.danmaku import DanmakuSaveType

MEBIBYTE = 1024 * 1024


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
    published_at: str
    added_at: str


@dataclass(frozen=True, slots=True)
class DownloadResources:
    """Frozen write policy derived from Scope and ResourceManifest."""

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
    """Turn a ResourceManifest plus a path and Scope into a pure download plan."""

    def plan(self, resources: ResourceManifest, path: Path, scope: Scope) -> DownloadPlan:
        selection = select_streams(resources, scope)
        video_meta = selection.video
        audio_meta = selection.audio
        suffix = resolve_output_suffix(video_meta, audio_meta, scope)
        output_directory, temporary_directory = resolve_output_directories(scope)
        paths = resolve_paths(output_directory, temporary_directory, path, suffix)

        _, video_save_codec = resolve_video_codecs(scope)
        attach_hvc1_tag = should_attach_hvc1_tag(video_meta, video_save_codec)
        if video_meta is not None and video_meta.codec == video_save_codec:
            video_save_codec = "copy"

        _, requested_audio_save_codec = resolve_audio_codecs(scope)
        audio_save_codec = (
            resolve_audio_save_codec(audio_meta.codec, requested_audio_save_codec, suffix)
            if audio_meta is not None
            else requested_audio_save_codec
        )

        fixed = bool(scope.danmaku.block_fixed)
        resource_plan = DownloadResources(
            subtitle_languages=tuple(lang for lang, _ in resources.subtitles),
            has_danmaku=bool(resources.danmaku_urls),
            danmaku_save_type=resolve_danmaku_format(scope) if resources.danmaku_urls else None,
            has_metadata=wants_metadata(scope),
            has_cover=resources.cover_url is not None,
            has_chapter_info=resources.chapter_info_url is not None,
            save_cover=should_save_cover(scope),
            danmaku_width=video_meta.width if video_meta is not None else 1920,
            danmaku_height=video_meta.height if video_meta is not None else 1080,
            metadata=MetadataPlan(
                published_at=_text(scope.output.metadata_premiered_format),
                added_at=TIME_FULL_FMT,
            ),
            danmaku=DanmakuPlan(
                font_size=_optional_int(scope.danmaku.font_size),
                font=_text(scope.danmaku.font),
                opacity=_float(scope.danmaku.opacity),
                display_region_ratio=_float(scope.danmaku.display_region_ratio),
                speed=_float(scope.danmaku.speed),
                block_top=bool(scope.danmaku.block_top) or fixed,
                block_bottom=bool(scope.danmaku.block_bottom) or fixed,
                block_scroll=bool(scope.danmaku.block_scroll),
                block_reverse=bool(scope.danmaku.block_reverse),
                block_special=bool(scope.danmaku.block_special),
                block_colorful=bool(scope.danmaku.block_colorful),
                block_keyword_patterns=_patterns(scope.danmaku.block_keyword_patterns),
            ),
        )
        return DownloadPlan(
            item=path.name,
            paths=paths,
            video=freeze_video_stream(video_meta, selection.video_index),
            audio=freeze_audio_stream(audio_meta, selection.audio_index),
            media_requested=resources.video_requested or resources.audio_requested,
            video_save_codec=video_save_codec,
            audio_save_codec=audio_save_codec,
            attach_hvc1_tag=attach_hvc1_tag,
            requires_audio_transcode_notice=(
                audio_meta is not None and audio_save_codec not in {requested_audio_save_codec, "copy"}
            ),
            overwrite=bool(scope.output.overwrite),
            block_size=resolve_block_size_bytes(scope),
            banned_mirrors_pattern=_optional_text(scope.network.banned_mirrors_pattern),
            resources=resource_plan,
        )


def resolve_output_directories(scope: Scope) -> tuple[Path, Path]:
    directory = scope.output.directory
    output_directory = Path() if directory is None else Path(directory)
    temporary = scope.output.temporary_directory
    temporary_directory = output_directory if temporary is None else Path(temporary)
    return output_directory, temporary_directory


def resolve_block_size_bytes(scope: Scope) -> int:
    value = scope.network.block_size
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("block_size must be a positive number")
    size = int(value * MEBIBYTE)
    if size < 1:
        raise ValueError("block_size must be a positive number")
    return size


def resolve_paths(base_output_dir: Path, base_temporary_dir: Path, path: Path, output_suffix: str) -> DownloadPaths:
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


def resolve_output_suffix(video: VideoUrlMeta | None, audio: AudioUrlMeta | None, scope: Scope) -> str:
    output_format = resolve_output_format(scope.output.format)
    audio_only_format = resolve_audio_only_output_format(scope.output.audio_only_format)
    _, audio_save_codec = resolve_audio_codecs(scope)
    if video is None:
        if audio_only_format != "infer":
            return f".{audio_only_format}"
        if audio is not None and audio.codec == "flac" and audio_save_codec in {"copy", "flac"}:
            return ".flac"
        if audio is not None and audio.codec == "eac3" and audio_save_codec in {"copy", "eac3"}:
            return ".mkv"
        return ".m4a"

    if output_format != "infer":
        return f".{output_format}"
    if audio is not None and audio.codec == "flac":
        return ".mkv"
    return ".mp4"


def freeze_video_stream(video: VideoUrlMeta | None, index: int | None) -> VideoStream | None:
    if video is None:
        return None
    assert index is not None
    return VideoStream(index=index, codec=video.codec, width=video.width, height=video.height, quality=video.quality)


def freeze_audio_stream(audio: AudioUrlMeta | None, index: int | None) -> AudioStream | None:
    if audio is None:
        return None
    assert index is not None
    return AudioStream(index=index, codec=audio.codec, quality=audio.quality)


def should_attach_hvc1_tag(video: VideoUrlMeta | None, video_save_codec: str) -> bool:
    """Whether the output needs the Apple-compatible hvc1 tag."""
    return (
        video is not None
        and video.quality != 126
        and (video_save_codec == "hevc" or (video_save_codec == "copy" and video.codec == "hevc"))
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


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("expected a string Scope value")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected a string Scope value")
    return value


def _float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected a numeric Scope value")
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("expected an integer Scope value")
    return value


def _patterns(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        raise ValueError("danmaku block keyword patterns must be a sequence of strings")
    return cast("tuple[str, ...]", value)
