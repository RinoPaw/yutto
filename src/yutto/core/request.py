from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yutto.stream import AudioCodec, AudioQuality, VideoCodec, VideoQuality
from yutto.utils.time import TIME_DATE_FMT


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpec(_RequestModel):
    """The source to resolve."""

    url: str


class AccessSpec(_RequestModel):
    """Authentication profile and access checks, without credential material."""

    auth_profile: str = "default"
    login_strict: bool = False
    vip_strict: bool = False


class SelectionSpec(_RequestModel):
    """Selection expression and filters for the current source selection domain."""

    expression: str | None = None
    skip_preview: bool = False
    start_time: str | None = None
    end_time: str | None = None


class ResourceSpec(_RequestModel):
    """Resources that should be present in the resulting download."""

    video: bool = True
    audio: bool = True
    danmaku: bool = True
    subtitle: bool = True
    metadata: bool = False
    cover: bool = True
    chapter_info: bool = True
    save_cover: bool = False
    ai_translation_language: str | None = None

    @model_validator(mode="after")
    def enable_save_cover_for_cover_only(self) -> Self:
        if self.save_cover and not self.cover:
            raise ValueError("save_cover requires cover")
        if self.cover and not any(
            (
                self.video,
                self.audio,
                self.danmaku,
                self.subtitle,
                self.metadata,
                self.chapter_info,
            )
        ):
            self.save_cover = True
        return self


class StreamSpec(_RequestModel):
    """Media stream quality and codec preferences."""

    video_quality: VideoQuality = 127
    audio_quality: AudioQuality = 30251
    video_download_codec: VideoCodec = "avc"
    video_save_codec: str = "copy"
    video_download_codec_priority: list[VideoCodec] | None = None
    audio_download_codec: AudioCodec = "mp4a"
    audio_save_codec: str = "copy"

    @model_validator(mode="after")
    def validate_video_codec_priority(self) -> Self:
        priority = self.video_download_codec_priority
        if priority is not None and not priority:
            raise ValueError("video_download_codec_priority must not be empty")
        if priority is not None and self.video_download_codec not in priority:
            raise ValueError("video_download_codec must be included in video_download_codec_priority")
        return self


class OutputSpec(_RequestModel):
    """Output paths, containers, and naming preferences."""

    directory: Path = Field(default_factory=Path)
    temporary_directory: Path | None = None
    format: Literal["infer", "mp4", "mkv", "mov"] = "infer"
    audio_only_format: Literal["infer", "m4a", "aac", "mp3", "flac", "mp4", "mkv", "mov"] = "infer"
    overwrite: bool = False
    subpath_template: str = "{auto}"
    metadata_format_premiered: str = TIME_DATE_FMT
    enforce_directory_boundary: bool = Field(default=False, exclude=True)


class NetworkSpec(_RequestModel):
    """Network access and transfer concurrency preferences."""

    proxy: str = "auto"
    fetch_workers: int = 8
    download_workers: int = 8
    block_size_bytes: int = 512 * 1024
    download_interval: int = 0
    banned_mirrors_pattern: str | None = None


class DanmakuSpec(_RequestModel):
    """Danmaku serialization, rendering, and filtering preferences."""

    format: Literal["xml", "ass", "protobuf"] = "ass"
    font_size: int | None = None
    font: str = "SimHei"
    opacity: float = 0.8
    display_region_ratio: float = 1.0
    speed: float = 1.0
    block_top: bool = False
    block_bottom: bool = False
    block_scroll: bool = False
    block_reverse: bool = False
    block_special: bool = False
    block_colorful: bool = False
    block_keyword_patterns: list[str] = Field(default_factory=list)


class DownloadRequest(_RequestModel):
    """A fully resolved, frontend-independent request to yutto's core."""

    source: SourceSpec
    access: AccessSpec = Field(default_factory=AccessSpec)
    batch: bool = Field(default=False, deprecated=True)
    with_extra_episodes: bool = False
    selection: SelectionSpec = Field(default_factory=SelectionSpec)
    resources: ResourceSpec = Field(default_factory=ResourceSpec)
    stream: StreamSpec = Field(default_factory=StreamSpec)
    output: OutputSpec = Field(default_factory=OutputSpec)
    network: NetworkSpec = Field(default_factory=NetworkSpec)
    danmaku: DanmakuSpec = Field(default_factory=DanmakuSpec)
