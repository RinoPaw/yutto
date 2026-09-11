from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from yutto.types import MultiLangSubtitle
    from yutto.utils.danmaku import DanmakuData
    from yutto.utils.metadata import ChapterInfoData


@dataclass(frozen=True, slots=True)
class Downloaded:
    """Resource bodies and temporary media files already fetched for one download."""

    video_path: Path | None = None
    audio_path: Path | None = None
    subtitles: tuple[MultiLangSubtitle, ...] = ()
    danmaku: DanmakuData | None = None
    cover_data: bytes | None = None
    chapter_info_data: tuple[ChapterInfoData, ...] = ()
