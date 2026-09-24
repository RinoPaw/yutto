from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yutto.types import AId, CId, CollectionId, EpisodeId, FId, MId, SeasonId, SeriesId
    from yutto.utils.metadata import ItemMetaData


@dataclass(slots=True, kw_only=True)
class Media:
    metadata: ItemMetaData


@dataclass(slots=True, kw_only=True)
class MediaItem(Media):
    index: int


@dataclass(slots=True, kw_only=True)
class MediaContainer(Media):
    items: tuple[Media, ...]


@dataclass(slots=True, kw_only=True)
class BangumiEpisode(MediaItem):
    """番剧中的一个剧集。"""

    episode_id: EpisodeId
    aid: AId
    cid: CId
    is_preview: bool = False


@dataclass(slots=True, kw_only=True)
class BangumiSeason(MediaContainer):
    """番剧的一季，拥有多个剧集。"""

    season_id: SeasonId
    items: tuple[BangumiEpisode, ...] = ()


@dataclass(slots=True, kw_only=True)
class CheeseEpisode(MediaItem):
    """课程中的一个剧集。"""

    episode_id: EpisodeId
    aid: AId
    cid: CId


@dataclass(slots=True, kw_only=True)
class CheeseSeason(MediaContainer):
    """课程（季），拥有多个课程剧集。"""

    season_id: SeasonId
    items: tuple[CheeseEpisode, ...] = ()


@dataclass(slots=True, kw_only=True)
class UgcPage(MediaItem):
    """UGC 投稿中的一个分 P。"""

    aid: AId
    cid: CId


@dataclass(slots=True, kw_only=True)
class UgcVideo(MediaContainer):
    """一个 UGC 投稿，拥有一个或多个分 P。"""

    aid: AId
    page_count: int = 1
    items: tuple[UgcPage, ...] = ()


@dataclass(slots=True, kw_only=True)
class UgcCollection(MediaContainer):
    """UP 主创建的视频合集（season）。"""

    collection_id: CollectionId
    items: tuple[UgcVideo, ...] = ()


@dataclass(slots=True, kw_only=True)
class UgcSeries(MediaContainer):
    """UP 主创建的视频系列（series）。"""

    series_id: SeriesId
    items: tuple[UgcVideo, ...] = ()


@dataclass(slots=True, kw_only=True)
class UgcFav(MediaContainer):
    """收藏夹。"""

    fid: FId
    items: tuple[UgcVideo, ...] = ()


@dataclass(slots=True, kw_only=True)
class UgcAllFavourites(MediaContainer):
    """用户创建的全部收藏夹。"""

    mid: MId
    items: tuple[UgcFav, ...] = ()


@dataclass(slots=True, kw_only=True)
class UgcWatchLater(MediaContainer):
    """稍后再看列表。"""

    items: tuple[UgcVideo, ...] = ()


@dataclass(slots=True, kw_only=True)
class UgcSpace(MediaContainer):
    """UP 主空间中的投稿列表。"""

    mid: MId
    items: tuple[UgcVideo, ...] = ()


__all__ = [
    "BangumiEpisode",
    "BangumiSeason",
    "CheeseEpisode",
    "CheeseSeason",
    "Media",
    "MediaContainer",
    "MediaItem",
    "UgcAllFavourites",
    "UgcCollection",
    "UgcFav",
    "UgcPage",
    "UgcSeries",
    "UgcSpace",
    "UgcVideo",
    "UgcWatchLater",
]
