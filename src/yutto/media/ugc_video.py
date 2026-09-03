from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yutto.media._abc import MediaContainer

if TYPE_CHECKING:
    from yutto.media.ugc_page import UgcPage
    from yutto.types import AvId


@dataclass(slots=True, kw_only=True)
class UgcVideo(MediaContainer):
    """一个 UGC 投稿，拥有一个或多个分 P。"""

    id: AvId
    items: list[UgcPage] = field(default_factory=list)
