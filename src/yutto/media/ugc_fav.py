from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yutto.media._abc import MediaContainer

if TYPE_CHECKING:
    from yutto.media.ugc_video import UgcVideo
    from yutto.types import BilibiliId


@dataclass(slots=True, kw_only=True)
class UgcFav(MediaContainer):
    """收藏夹。"""

    id: BilibiliId
    items: list[UgcVideo] = field(default_factory=list)
