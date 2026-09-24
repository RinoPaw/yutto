from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from yutto.utils.danmaku import DanmakuSaveType, DanmakuSourceType


@dataclass(frozen=True, slots=True)
class DownloadedSubtitleLine:
    content: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class DownloadedSubtitle:
    lang: str
    lines: tuple[DownloadedSubtitleLine, ...]


@dataclass(frozen=True, slots=True)
class DownloadedDanmaku:
    source_type: DanmakuSourceType | None
    save_type: DanmakuSaveType | None
    data: tuple[str | bytes, ...] = ()


@dataclass(frozen=True, slots=True)
class DownloadedChapter:
    start: int
    end: int
    content: str


@dataclass(frozen=True, slots=True)
class Downloaded:
    """Resources already fetched for one download, deeply immutable after acquisition."""

    video_path: Path | None = None
    audio_path: Path | None = None
    cover_path: Path | None = None
    subtitles: tuple[DownloadedSubtitle, ...] = ()
    danmaku: DownloadedDanmaku | None = None
    chapters: tuple[DownloadedChapter, ...] = ()
