from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yutto.media._abc import MediaContainer

if TYPE_CHECKING:
    from yutto.media.ugc_video import UgcVideo
    from yutto.types import CollectionId


@dataclass(slots=True, kw_only=True)
class UgcCollection(MediaContainer):
    """UP 主创建的视频合集（season）。"""

    id: CollectionId
    items: list[UgcVideo] = field(default_factory=list)
