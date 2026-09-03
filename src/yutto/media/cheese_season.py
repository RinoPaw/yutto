from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yutto.media._abc import MediaContainer

if TYPE_CHECKING:
    from yutto.media.cheese_episode import CheeseEpisode
    from yutto.types import SeasonId


@dataclass(slots=True, kw_only=True)
class CheeseSeason(MediaContainer):
    """课程（季），拥有多个课程剧集。"""

    id: SeasonId
    items: list[CheeseEpisode] = field(default_factory=list)
