from __future__ import annotations

from yutto.media._abc import Media, MediaContainer, MediaItem
from yutto.media.bangumi_episode import BangumiEpisode
from yutto.media.bangumi_season import BangumiSeason
from yutto.media.cheese_episode import CheeseEpisode
from yutto.media.cheese_season import CheeseSeason
from yutto.media.ugc_collection import UgcCollection
from yutto.media.ugc_list import UgcList
from yutto.media.ugc_page import UgcPage
from yutto.media.ugc_series import UgcSeries
from yutto.media.ugc_video import UgcVideo

__all__ = [
    "BangumiEpisode",
    "BangumiSeason",
    "CheeseEpisode",
    "CheeseSeason",
    "Media",
    "MediaContainer",
    "MediaItem",
    "UgcCollection",
    "UgcList",
    "UgcPage",
    "UgcSeries",
    "UgcVideo",
]
