from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yutto.media._abc import MediaContainer

if TYPE_CHECKING:
    from yutto.media.bangumi_episode import BangumiEpisode
    from yutto.types import MediaId, SeasonId


@dataclass(slots=True, kw_only=True)
class BangumiSeason(MediaContainer):
    """番剧的一季，拥有多个剧集。"""

    id: SeasonId
    items: list[BangumiEpisode] = field(default_factory=list)
