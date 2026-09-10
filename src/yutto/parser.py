from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from yutto.exceptions import WrongArgumentError
from yutto.source import (
    AmbiguousSource,
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
_URL_END = r"(?:/(?:[?#].*)?|(?:[?#].*)?)"

_UGC_AV_URL = re.compile(rf"{_BILIBILI}/video/av(?P<aid>[0-9]+){_URL_END}", re.IGNORECASE)
_UGC_BV_URL = re.compile(rf"{_BILIBILI}/video/(?P<bvid>BV[A-Za-z0-9]+){_URL_END}", re.IGNORECASE)
_B23_AV_URL = re.compile(rf"{_B23}/av(?P<aid>[0-9]+){_URL_END}", re.IGNORECASE)
_B23_BV_URL = re.compile(rf"{_B23}/(?P<bvid>BV[A-Za-z0-9]+){_URL_END}", re.IGNORECASE)
_FESTIVAL_URL = re.compile(rf"{_BILIBILI}/festival/", re.IGNORECASE)

_BANGUMI_EP_URL = re.compile(rf"{_BILIBILI}/bangumi/play/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
_BANGUMI_SS_URL = re.compile(rf"{_BILIBILI}/bangumi/play/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)
_BANGUMI_MD_URL = re.compile(rf"{_BILIBILI}/bangumi/media/md(?P<media_id>[0-9]+){_URL_END}", re.IGNORECASE)
_B23_EP_URL = re.compile(rf"{_B23}/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
_B23_SS_URL = re.compile(rf"{_B23}/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)

_CHEESE_EP_URL = re.compile(rf"{_BILIBILI}/cheese/play/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
_CHEESE_SS_URL = re.compile(rf"{_BILIBILI}/cheese/play/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)

_PLAYLIST_URL = re.compile(rf"{_BILIBILI}/list/(?P<mid>[0-9]+){_URL_END}", re.IGNORECASE)
_SPACE_LIST_URL = re.compile(
    rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+){_URL_END}", re.IGNORECASE
)
_FAVOURITE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE)
_WATCH_LATER_URL = re.compile(rf"{_BILIBILI}/(?:list/)?watchlater{_URL_END}", re.IGNORECASE)
_SPACE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)(?:/video)?{_URL_END}", re.IGNORECASE)


def _single_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if values is None:
        return None
    if len(values) != 1:
        raise WrongArgumentError(f"参数 {key} 重复出现（值: {values}）")
    return values[0]


def _parse_page(query: dict[str, list[str]]) -> int | None:
    page = _single_query_value(query, "p")
    if page is None:
        return None
    try:
        value = int(page)
    except ValueError:
        raise WrongArgumentError(f"page `{page}` 不是整数") from None
    if value < 1:
        raise WrongArgumentError(f"page `{page}` 应为正整数")
    return value


def _parse_avid_from_query(query: dict[str, list[str]]) -> AId | BvId | None:
    bvid = _single_query_value(query, "bvid")
    aid = _single_query_value(query, "aid")
    oid = _single_query_value(query, "oid")
    values = [
        BvId(bvid) if bvid else None,
        AId(aid) if aid else None,
        AId(oid) if oid else None,
    ]
    values = [value for value in values if value]
    return values[0] if values else None


def _parse_ugc_video(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    if match := _UGC_AV_URL.fullmatch(value):
        avid: AId | BvId = AId(match.group("aid"))
    elif match := _UGC_BV_URL.fullmatch(value):
        avid = BvId(match.group("bvid"))
    elif match := _B23_AV_URL.fullmatch(value):
        avid = AId(match.group("aid"))
    elif match := _B23_BV_URL.fullmatch(value):
        avid = BvId(match.group("bvid"))
    elif _FESTIVAL_URL.match(value):
        avid = _parse_avid_from_query(query)
        if avid is None:
            return None
    elif match := _AV_ID.match(value):
        avid = AId(match.group("aid"))
    elif match := _BV_ID.match(value):
        avid = BvId(match.group("bvid"))
    else:
        return None
    return UgcVideoSource(id=avid, page=_parse_page(query))


def _parse_bangumi(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    del query
    if match := _BANGUMI_SS_URL.fullmatch(value):
        return BangumiSeasonSource(id=SeasonId(match.group("season_id")))
    if match := _BANGUMI_EP_URL.fullmatch(value):
        return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")))
    if match := _BANGUMI_MD_URL.fullmatch(value):
        return BangumiSeasonSource(id=MediaId(match.group("media_id")))
    if match := _B23_SS_URL.fullmatch(value):
        return BangumiSeasonSource(id=SeasonId(match.group("season_id")))
    if match := _B23_EP_URL.fullmatch(value):
        return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")))
    if match := _MD_ID.fullmatch(value):
        return BangumiSeasonSource(id=MediaId(match.group("media_id")))
    return None


def _parse_cheese(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    del query
    if match := _CHEESE_EP_URL.fullmatch(value):
        return CheeseEpisodeSource(id=EpisodeId(match.group("episode_id")))
    if match := _CHEESE_SS_URL.fullmatch(value):
        return CheeseSeasonSource(id=SeasonId(match.group("season_id")))
    return None


def _parse_series(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    if _PLAYLIST_URL.fullmatch(value):
        sid = _single_query_value(query, "sid")
        if sid is None:
            return None
        return UgcSeriesSource(id=SeriesId(sid))
    if match := _SPACE_LIST_URL.fullmatch(value):
        if _single_query_value(query, "type") != "series":
            return None
        return UgcSeriesSource(id=SeriesId(match.group("list_id")))
    return None


def _parse_collection(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    if match := _SPACE_LIST_URL.fullmatch(value):
        if _single_query_value(query, "type") != "season":
            return None
        return UgcCollectionSource(
            id=CollectionId(match.group("list_id")),
            owner_id=MId(match.group("mid")),
        )
    if match := _FAVOURITE_URL.fullmatch(value):
        if _single_query_value(query, "ftype") != "collect":
            return None
        fid = _single_query_value(query, "fid")
        if fid is None:
            return None
        return UgcCollectionSource(
            id=CollectionId(fid),
            owner_id=MId(match.group("mid")),
        )
    return None


def _parse_favourite(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    match = _FAVOURITE_URL.fullmatch(value)
    if match is None:
        return None
    if _single_query_value(query, "ftype") == "collect":
        return None
    fid = _single_query_value(query, "fid")
    if fid is not None:
        return UgcFavSource(id=FId(fid))
    if not query:
        return UgcAllFavouritesSource(id=MId(match.group("mid")))
    return None


def _parse_watch_later(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    del query
    if _WATCH_LATER_URL.fullmatch(value):
        return UgcWatchLaterSource(id=BilibiliId("watchlater"))
    return None


def _parse_space(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    del query
    if match := _SPACE_URL.fullmatch(value):
        return UgcSpaceSource(id=MId(match.group("mid")))
    return None


def _parse_ambiguous(value: str, query: dict[str, list[str]]) -> MediaSource | None:
    del query
    if match := _EP_ID.fullmatch(value):
        episode_id = EpisodeId(match.group("episode_id"))
        return AmbiguousSource(
            id=episode_id,
            candidates=(
                BangumiEpisodeSource(id=episode_id),
                CheeseEpisodeSource(id=episode_id),
            ),
        )
    if match := _SS_ID.fullmatch(value):
        season_id = SeasonId(match.group("season_id"))
        return AmbiguousSource(
            id=season_id,
            candidates=(
                BangumiSeasonSource(id=season_id),
                CheeseSeasonSource(id=season_id),
            ),
        )
    return None


_PARSERS = (
    _parse_ugc_video,
    _parse_bangumi,
    _parse_cheese,
    _parse_series,
    _parse_collection,
    _parse_favourite,
    _parse_watch_later,
    _parse_space,
    _parse_ambiguous,
)


def parse(value: str) -> MediaSource | None:
    value = value.strip()
    if not value:
        return None

    query = parse_qs(urlparse(value).query, keep_blank_values=True)
    for parser in _PARSERS:
        source = parser(value, query)
        if source is not None:
            return source
    return None
