from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yutto.media._abc import MediaContainer

if TYPE_CHECKING:
    from yutto.media.ugc_video import UgcVideo


@dataclass(slots=True, kw_only=True)
class UgcWatchLater(MediaContainer):
    """稍后再看列表。"""

    items: list[UgcVideo] = field(default_factory=list)
