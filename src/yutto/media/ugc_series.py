from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yutto.media._abc import MediaContainer

if TYPE_CHECKING:
    from yutto.media.ugc_video import UgcVideo
    from yutto.types import SeriesId


@dataclass(slots=True, kw_only=True)
class UgcSeries(MediaContainer):
    """UP 主创建的视频系列（series）。"""

    id: SeriesId
    items: list[UgcVideo] = field(default_factory=list)
