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

_VIDEO_AV_PATH = re.compile(r"/video/av(?P<aid>[0-9]+)/?", re.IGNORECASE)
_VIDEO_BV_PATH = re.compile(r"/video/(?P<bvid>BV[A-Za-z0-9]+)/?", re.IGNORECASE)
_BANGUMI_EP_PATH = re.compile(r"/bangumi/play/ep(?P<episode_id>[0-9]+)/?", re.IGNORECASE)
_BANGUMI_SS_PATH = re.compile(r"/bangumi/play/ss(?P<season_id>[0-9]+)/?", re.IGNORECASE)
_BANGUMI_MD_PATH = re.compile(r"/bangumi/media/md(?P<media_id>[0-9]+)/?", re.IGNORECASE)
_CHEESE_EP_PATH = re.compile(r"/cheese/play/ep(?P<episode_id>[0-9]+)/?", re.IGNORECASE)
_CHEESE_SS_PATH = re.compile(r"/cheese/play/ss(?P<season_id>[0-9]+)/?", re.IGNORECASE)
_PLAYLIST_PATH = re.compile(r"/list/(?P<mid>[0-9]+)/?", re.IGNORECASE)
_B23_AV_PATH = re.compile(r"/av(?P<aid>[0-9]+)/?", re.IGNORECASE)
_B23_BV_PATH = re.compile(r"/(?P<bvid>BV[A-Za-z0-9]+)/?", re.IGNORECASE)
_B23_EP_PATH = re.compile(r"/ep(?P<episode_id>[0-9]+)/?", re.IGNORECASE)
_B23_SS_PATH = re.compile(r"/ss(?P<season_id>[0-9]+)/?", re.IGNORECASE)
_SPACE_LIST_PATH = re.compile(r"/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+)/?", re.IGNORECASE)
_SPACE_FAVOURITE_PATH = re.compile(r"/(?P<mid>[0-9]+)/favlist/?", re.IGNORECASE)
_SPACE_PATH = re.compile(r"/(?P<mid>[0-9]+)(?:/video)?/?", re.IGNORECASE)


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

    parsed = urlparse(value)
    query = parse_qs(parsed.query, keep_blank_values=True)

    # Short IDs are the cheapest and most common forms to identify.
    if match := _AV_ID.match(value):
        return UgcVideoSource(id=AId(match.group("aid")), page=_page(query))
    if match := _BV_ID.match(value):
        return UgcVideoSource(id=BvId(match.group("bvid")), page=_page(query))
    if match := _MD_ID.fullmatch(value):
        return BangumiSeasonSource(id=MediaId(match.group("media_id")))
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

    if parsed.scheme.lower() not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    path = parsed.path

    if host in {"bilibili.com", "www.bilibili.com"}:
        if path.lower().startswith("/video/"):
            if match := _VIDEO_AV_PATH.fullmatch(path):
                return UgcVideoSource(id=AId(match.group("aid")), page=_page(query))
            if match := _VIDEO_BV_PATH.fullmatch(path):
                return UgcVideoSource(id=BvId(match.group("bvid")), page=_page(query))
            return None

        if path.lower().startswith("/festival/"):
            avid = _festival_avid(query)
            return UgcVideoSource(id=avid, page=_page(query)) if avid is not None else None

        if path.lower().startswith("/bangumi/play/"):
            if match := _BANGUMI_SS_PATH.fullmatch(path):
                return BangumiSeasonSource(id=SeasonId(match.group("season_id")))
            if match := _BANGUMI_EP_PATH.fullmatch(path):
                return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")))
            return None

        if path.lower().startswith("/bangumi/media/"):
            if match := _BANGUMI_MD_PATH.fullmatch(path):
                return BangumiSeasonSource(id=MediaId(match.group("media_id")))
            return None

        if path.lower().startswith("/cheese/play/"):
            if match := _CHEESE_EP_PATH.fullmatch(path):
                return CheeseEpisodeSource(id=EpisodeId(match.group("episode_id")))
            if match := _CHEESE_SS_PATH.fullmatch(path):
                return CheeseSeasonSource(id=SeasonId(match.group("season_id")))
            return None

        if path.lower() in {"/watchlater", "/watchlater/", "/list/watchlater", "/list/watchlater/"}:
            return UgcWatchLaterSource(id=BilibiliId("watchlater"))

        if match := _PLAYLIST_PATH.fullmatch(path):
            sid = _query_value(query, "sid")
            return UgcSeriesSource(id=SeriesId(sid)) if sid is not None else None

        return None

    if host == "b23.tv":
        if match := _B23_AV_PATH.fullmatch(path):
            return UgcVideoSource(id=AId(match.group("aid")), page=_page(query))
        if match := _B23_BV_PATH.fullmatch(path):
            return UgcVideoSource(id=BvId(match.group("bvid")), page=_page(query))
        if match := _B23_SS_PATH.fullmatch(path):
            return BangumiSeasonSource(id=SeasonId(match.group("season_id")))
        if match := _B23_EP_PATH.fullmatch(path):
            return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")))
        return None

    if host == "space.bilibili.com":
        if match := _SPACE_LIST_PATH.fullmatch(path):
            list_type = _query_value(query, "type")
            if list_type == "series":
                return UgcSeriesSource(id=SeriesId(match.group("list_id")))
            if list_type == "season":
                return UgcCollectionSource(
                    id=CollectionId(match.group("list_id")),
                    owner_id=MId(match.group("mid")),
                )
            return None

        if match := _SPACE_FAVOURITE_PATH.fullmatch(path):
            mid = MId(match.group("mid"))
            ftype = _query_value(query, "ftype")
            if ftype == "collect":
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

        if match := _SPACE_PATH.fullmatch(path):
            return UgcSpaceSource(id=MId(match.group("mid")))

    return None
