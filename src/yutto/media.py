from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import TYPE_CHECKING, Any

from yutto.types import BilibiliId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    from yutto.types import AvId, CId, CollectionId, EpisodeId, FId, MId, SeasonId, SeriesId


def _to_plain(value: Any) -> Any:
    if isinstance(value, BilibiliId):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field_.name: _to_plain(getattr(value, field_.name)) for field_ in fields(value)}
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value


@dataclass(slots=True, kw_only=True)
class Media:
    metadata: ItemMetaData

    def to_dict(self) -> dict[str, Any]:
        result = _to_plain(self)
        assert isinstance(result, dict)
        return result


@dataclass(slots=True, kw_only=True)
class MediaItem(Media):
    pass


@dataclass(slots=True, kw_only=True)
class MediaContainer(Media):
    items: list[Media]


@dataclass(slots=True, kw_only=True)
class BangumiEpisode(MediaItem):
    """番剧中的一个剧集。"""

    episode_id: EpisodeId
    avid: AvId
    cid: CId


@dataclass(slots=True, kw_only=True)
class BangumiSeason(MediaContainer):
    """番剧的一季，拥有多个剧集。"""

    season_id: SeasonId
    items: list[BangumiEpisode] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class CheeseEpisode(MediaItem):
    """课程中的一个剧集。"""

    episode_id: EpisodeId
    avid: AvId
    cid: CId


@dataclass(slots=True, kw_only=True)
class CheeseSeason(MediaContainer):
    """课程（季），拥有多个课程剧集。"""

    season_id: SeasonId
    items: list[CheeseEpisode] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class UgcPage(MediaItem):
    """UGC 投稿中的一个分 P。"""

    avid: AvId
    cid: CId


@dataclass(slots=True, kw_only=True)
class UgcVideo(MediaContainer):
    """一个 UGC 投稿，拥有一个或多个分 P。"""

    avid: AvId
    items: list[UgcPage] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class UgcCollection(MediaContainer):
    """UP 主创建的视频合集（season）。"""

    collection_id: CollectionId
    items: list[UgcVideo] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class UgcSeries(MediaContainer):
    """UP 主创建的视频系列（series）。"""

    series_id: SeriesId
    items: list[UgcVideo] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class UgcFav(MediaContainer):
    """收藏夹。"""

    fid: FId
    items: list[UgcVideo] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class UgcWatchLater(MediaContainer):
    """稍后再看列表。"""

    items: list[UgcVideo] = field(default_factory=list)


@dataclass(slots=True, kw_only=True)
class UgcSpace(MediaContainer):
    """UP 主空间中的投稿列表。"""

    mid: MId
    items: list[UgcVideo] = field(default_factory=list)


__all__ = [
    "BangumiEpisode",
    "BangumiSeason",
    "CheeseEpisode",
    "CheeseSeason",
    "Media",
    "MediaContainer",
    "MediaItem",
    "UgcCollection",
    "UgcFav",
    "UgcPage",
    "UgcSeries",
    "UgcSpace",
    "UgcVideo",
    "UgcWatchLater",
]
