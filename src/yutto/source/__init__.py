from __future__ import annotations

from yutto.source._abc import AmbiguousSource, Source, SourceOptions
from yutto.source.bangumi_episode_source import BangumiEpisodeSource
from yutto.source.bangumi_season_source import BangumiSeasonSource
from yutto.source.cheese_episode_source import CheeseEpisodeSource
from yutto.source.cheese_season_source import CheeseSeasonSource
from yutto.source.ugc_collection_source import UgcCollectionSource
from yutto.source.ugc_fav_source import UgcFavSource
from yutto.source.ugc_series_source import UgcSeriesSource
from yutto.source.ugc_video_source import UgcVideoSource
from yutto.source.ugc_watch_later_source import UgcWatchLaterSource

__all__ = [
    "AmbiguousSource",
    "BangumiEpisodeSource",
    "BangumiSeasonSource",
    "CheeseEpisodeSource",
    "CheeseSeasonSource",
    "Source",
    "SourceOptions",
    "UgcCollectionSource",
    "UgcFavSource",
    "UgcSeriesSource",
    "UgcVideoSource",
    "UgcWatchLaterSource",
]
