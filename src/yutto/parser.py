from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from yutto.exceptions import WrongArgumentError
from yutto.source import (
    AmbiguousEpisodeSource,
    AmbiguousSeasonSource,
    BangumiEpisodeSource,
    BangumiSeasonSource,
    CheeseEpisodeSource,
    CheeseSeasonSource,
    MediaSource,
    UgcAllFavouritesSource,
    UgcCollectionSource,
    UgcFavSource,
    UgcSeriesSource,
    UgcSpaceSource,
    UgcVideoSource,
    UgcWatchLaterSource,
)
from yutto.types import (
    AId,
    BilibiliId,
    BvId,
    CollectionId,
    EpisodeId,
    FId,
    MediaId,
    MId,
    SeasonId,
    SeriesId,
)

_AV_ID = re.compile(r"av(?P<aid>[0-9]+)", re.IGNORECASE)
_BV_ID = re.compile(r"(?P<bvid>BV[A-Za-z0-9]+)", re.IGNORECASE)
_EP_ID = re.compile(r"ep(?P<episode_id>[0-9]+)", re.IGNORECASE)
_SS_ID = re.compile(r"ss(?P<season_id>[0-9]+)", re.IGNORECASE)
_MD_ID = re.compile(r"md(?P<media_id>[0-9]+)", re.IGNORECASE)

_BILIBILI = r"https?://(?:www\.)?bilibili\.com"
_SPACE_BILIBILI = r"https?://space\.bilibili\.com"
_B23 = r"https?://b23\.tv"
_URL_END = r"/?(?:[?#].*)?"

# Common direct links first. The patterns are intentionally complete URLs so
# the matching order itself documents which inputs yutto accepts.
_UGC_BV_URL = re.compile(rf"{_BILIBILI}/video/(?P<bvid>BV[A-Za-z0-9]+){_URL_END}", re.IGNORECASE)
_UGC_AV_URL = re.compile(rf"{_BILIBILI}/video/av(?P<aid>[0-9]+){_URL_END}", re.IGNORECASE)
_BANGUMI_EP_URL = re.compile(rf"{_BILIBILI}/bangumi/play/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
_BANGUMI_SS_URL = re.compile(rf"{_BILIBILI}/bangumi/play/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)
_CHEESE_EP_URL = re.compile(rf"{_BILIBILI}/cheese/play/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
_CHEESE_SS_URL = re.compile(rf"{_BILIBILI}/cheese/play/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)

_B23_BV_URL = re.compile(rf"{_B23}/(?P<bvid>BV[A-Za-z0-9]+){_URL_END}", re.IGNORECASE)
_B23_AV_URL = re.compile(rf"{_B23}/av(?P<aid>[0-9]+){_URL_END}", re.IGNORECASE)
_B23_EP_URL = re.compile(rf"{_B23}/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
_B23_SS_URL = re.compile(rf"{_B23}/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)

# Less common and query-disambiguated forms follow the unambiguous hot path.
_BANGUMI_MD_URL = re.compile(rf"{_BILIBILI}/bangumi/media/md(?P<media_id>[0-9]+){_URL_END}", re.IGNORECASE)
_WATCH_LATER_URL = re.compile(rf"{_BILIBILI}/(?:list/)?watchlater{_URL_END}", re.IGNORECASE)
_PLAYLIST_URL = re.compile(rf"{_BILIBILI}/list/(?P<mid>[0-9]+){_URL_END}", re.IGNORECASE)
_SPACE_LIST_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+){_URL_END}", re.IGNORECASE)
_FAVOURITE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE)
_SPACE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)(?:/video)?{_URL_END}", re.IGNORECASE)
_FESTIVAL_URL = re.compile(rf"{_BILIBILI}/festival/.*", re.IGNORECASE)


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query, keep_blank_values=True)


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if values is None:
        return None
    if len(values) != 1:
        raise WrongArgumentError(f"参数 {key} 重复出现（值: {values}）")
    return values[0]


def _page(query: dict[str, list[str]]) -> int | None:
    page = _query_value(query, "p")
    if page is None:
        return None
    try:
        value = int(page)
    except ValueError:
        raise WrongArgumentError(f"page `{page}` 不是整数") from None
    if value < 1:
        raise WrongArgumentError(f"page `{page}` 应为正整数")
    return value


def _festival_avid(query: dict[str, list[str]]) -> AId | BvId | None:
    bvid = _query_value(query, "bvid")
    aid = _query_value(query, "aid")
    oid = _query_value(query, "oid")
    if bvid:
        return BvId(bvid)
    if aid:
        return AId(aid)
    if oid:
        return AId(oid)
    return None


def parse(value: str) -> MediaSource | None:
    value = value.strip()
    if not value:
        return None

    # Short IDs stay first: no URL parsing is needed unless the UGC shortcut
    # actually carries a query string such as ?p=3.
    if match := _AV_ID.match(value):
        return UgcVideoSource(id=AId(match.group("aid")), page=_page(_query(value)))
    if match := _BV_ID.match(value):
        return UgcVideoSource(id=BvId(match.group("bvid")), page=_page(_query(value)))
    if match := _MD_ID.fullmatch(value):
        return BangumiSeasonSource(id=MediaId(match.group("media_id")))
    if match := _EP_ID.fullmatch(value):
        return AmbiguousEpisodeSource(id=EpisodeId(match.group("episode_id")))
    if match := _SS_ID.fullmatch(value):
        return AmbiguousSeasonSource(id=SeasonId(match.group("season_id")))

    # Common complete URLs. Query parsing happens only after a matching rule
    # needs it, so unrelated patterns do not repeatedly decompose the input.
    if match := _UGC_BV_URL.fullmatch(value):
        return UgcVideoSource(id=BvId(match.group("bvid")), page=_page(_query(value)))
    if match := _UGC_AV_URL.fullmatch(value):
        return UgcVideoSource(id=AId(match.group("aid")), page=_page(_query(value)))
    if match := _BANGUMI_EP_URL.fullmatch(value):
        return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")))
    if match := _BANGUMI_SS_URL.fullmatch(value):
        return BangumiSeasonSource(id=SeasonId(match.group("season_id")))
    if match := _CHEESE_EP_URL.fullmatch(value):
        return CheeseEpisodeSource(id=EpisodeId(match.group("episode_id")))
    if match := _CHEESE_SS_URL.fullmatch(value):
        return CheeseSeasonSource(id=SeasonId(match.group("season_id")))

    if match := _B23_BV_URL.fullmatch(value):
        return UgcVideoSource(id=BvId(match.group("bvid")), page=_page(_query(value)))
    if match := _B23_AV_URL.fullmatch(value):
        return UgcVideoSource(id=AId(match.group("aid")), page=_page(_query(value)))
    if match := _B23_EP_URL.fullmatch(value):
        return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")))
    if match := _B23_SS_URL.fullmatch(value):
        return BangumiSeasonSource(id=SeasonId(match.group("season_id")))

    if match := _BANGUMI_MD_URL.fullmatch(value):
        return BangumiSeasonSource(id=MediaId(match.group("media_id")))
    if _WATCH_LATER_URL.fullmatch(value):
        return UgcWatchLaterSource(id=BilibiliId("watchlater"))

    if _PLAYLIST_URL.fullmatch(value):
        sid = _query_value(_query(value), "sid")
        return UgcSeriesSource(id=SeriesId(sid)) if sid is not None else None

    if match := _SPACE_LIST_URL.fullmatch(value):
        list_type = _query_value(_query(value), "type")
        if list_type == "series":
            return UgcSeriesSource(id=SeriesId(match.group("list_id")))
        if list_type == "season":
            return UgcCollectionSource(
                id=CollectionId(match.group("list_id")),
                owner_id=MId(match.group("mid")),
            )
        return None

    if match := _FAVOURITE_URL.fullmatch(value):
        query = _query(value)
        mid = MId(match.group("mid"))
        if _query_value(query, "ftype") == "collect":
            fid = _query_value(query, "fid")
            if fid is None:
                return None
            return UgcCollectionSource(id=CollectionId(fid), owner_id=mid)

        fid = _query_value(query, "fid")
        if fid is not None:
            return UgcFavSource(id=FId(fid))
        if not query:
            return UgcAllFavouritesSource(id=mid)
        return None

    if match := _SPACE_URL.fullmatch(value):
        return UgcSpaceSource(id=MId(match.group("mid")))

    if _FESTIVAL_URL.fullmatch(value):
        query = _query(value)
        avid = _festival_avid(query)
        return UgcVideoSource(id=avid, page=_page(query)) if avid is not None else None

    return None
