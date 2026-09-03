from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto.media._abc import MediaItem

if TYPE_CHECKING:
    from yutto.types import EpisodeId


@dataclass(slots=True, kw_only=True)
class BangumiEpisode(MediaItem):
    """番剧中的一个可下载剧集。"""

    id: EpisodeId
