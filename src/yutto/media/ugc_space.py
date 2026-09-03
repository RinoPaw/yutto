from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yutto.media._abc import MediaContainer

if TYPE_CHECKING:
    from yutto.media.ugc_video import UgcVideo
    from yutto.types import Mid


@dataclass(slots=True, kw_only=True)
class UgcSpace(MediaContainer):
    """UP 主空间中的投稿列表。"""

    id: Mid
    items: list[UgcVideo] = field(default_factory=list)
