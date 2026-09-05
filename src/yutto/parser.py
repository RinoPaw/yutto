from __future__ import annotations

import re
from abc import ABC, abstractmethod
from urllib.parse import parse_qs, urlparse

from yutto.exceptions import WrongArgumentError
from yutto.source import (
    AmbiguousSource,
    BangumiEpisodeSource,
    BangumiSeasonSource,
    CheeseEpisodeSource,
    CheeseSeasonSource,
    Source,
    SourceOptions,
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


class Parser(ABC):
    @abstractmethod
    def parse(self, url: str, options: SourceOptions) -> Source | None:
        raise NotImplementedError

    @staticmethod
    def _single_query_value(query: dict[str, list[str]], key: str) -> str | None:
        values = query.get(key)
        if values is None:
            return None
        if len(values) != 1:
            raise WrongArgumentError(f"参数 {key} 重复出现（值: {values}）")
        return values[0]


class UgcVideoParser(Parser):
    _UGC_AV_URL = re.compile(rf"{_BILIBILI}/video/av(?P<aid>[0-9]+){_URL_END}", re.IGNORECASE)
    _UGC_BV_URL = re.compile(rf"{_BILIBILI}/video/(?P<bvid>BV[A-Za-z0-9]+){_URL_END}", re.IGNORECASE)
    _B23_AV_URL = re.compile(rf"{_B23}/av(?P<aid>[0-9]+){_URL_END}", re.IGNORECASE)
    _B23_BV_URL = re.compile(rf"{_B23}/(?P<bvid>BV[A-Za-z0-9]+){_URL_END}", re.IGNORECASE)
    _FESTIVAL_URL = re.compile(rf"{_BILIBILI}/festival/", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        avid = self._parse_avid(url, query)
        if avid is None:
            return None
        return UgcVideoSource(
            id=avid,
            page=self._parse_page(query),
            options=options,
        )

    def _parse_avid(self, url: str, query: dict[str, list[str]]) -> AId | BvId | None:
        if match := self._UGC_AV_URL.fullmatch(url):
            return AId(match.group("aid"))
        if match := self._UGC_BV_URL.fullmatch(url):
            return BvId(match.group("bvid"))
        if match := self._B23_AV_URL.fullmatch(url):
            return AId(match.group("aid"))
        if match := self._B23_BV_URL.fullmatch(url):
            return BvId(match.group("bvid"))
        if self._FESTIVAL_URL.match(url):
            return self._parse_avid_from_query(query)
        if match := _AV_ID.match(url):
            return AId(match.group("aid"))
        if match := _BV_ID.match(url):
            return BvId(match.group("bvid"))
        return None

    def _parse_page(self, query: dict[str, list[str]]) -> int | None:
        page = self._single_query_value(query, "p")
        if page is None:
            return None
        try:
            return int(page)
        except ValueError:
            raise WrongArgumentError(f"page `{page}` 不是整数") from None

    def _parse_avid_from_query(self, query: dict[str, list[str]]) -> AId | BvId | None:
        bvid = self._single_query_value(query, "bvid")
        aid = self._single_query_value(query, "aid")
        oid = self._single_query_value(query, "oid")
        values = [
            BvId(bvid) if bvid else None,
            AId(aid) if aid else None,
            AId(oid) if oid else None,
        ]
        values = [value for value in values if value]
        return values[0]


class BangumiParser(Parser):
    _BANGUMI_EP_URL = re.compile(
        rf"{_BILIBILI}/bangumi/play/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE
    )
    _BANGUMI_SS_URL = re.compile(
        rf"{_BILIBILI}/bangumi/play/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE
    )
    _BANGUMI_MD_URL = re.compile(
        rf"{_BILIBILI}/bangumi/media/md(?P<media_id>[0-9]+){_URL_END}", re.IGNORECASE
    )
    _B23_EP_URL = re.compile(rf"{_B23}/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _B23_SS_URL = re.compile(rf"{_B23}/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> BangumiEpisodeSource | BangumiSeasonSource | None:
        if match := self._BANGUMI_SS_URL.fullmatch(url):
            return BangumiSeasonSource(id=SeasonId(match.group("season_id")), options=options)
        if match := self._BANGUMI_EP_URL.fullmatch(url):
            return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")), options=options)
        if match := self._BANGUMI_MD_URL.fullmatch(url):
            return BangumiSeasonSource(id=MediaId(match.group("media_id")), options=options)
        if match := self._B23_SS_URL.fullmatch(url):
            return BangumiSeasonSource(id=SeasonId(match.group("season_id")), options=options)
        if match := self._B23_EP_URL.fullmatch(url):
            return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")), options=options)
        if match := _MD_ID.fullmatch(url):
            return BangumiSeasonSource(id=MediaId(match.group("media_id")), options=options)
        return None


class CheeseParser(Parser):
    _CHEESE_EP_URL = re.compile(
        r"https?://(?:www\.)?bilibili\.com/cheese/play/ep(?P<episode_id>[0-9]+)/?", re.IGNORECASE
    )
    _CHEESE_SS_URL = re.compile(
        r"https?://(?:www\.)?bilibili\.com/cheese/play/ss(?P<season_id>[0-9]+)/?", re.IGNORECASE
    )

    def parse(self, url: str, options: SourceOptions) -> CheeseEpisodeSource | CheeseSeasonSource | None:
        if match := self._CHEESE_EP_URL.fullmatch(url):
            return CheeseEpisodeSource(id=EpisodeId(match.group("episode_id")), options=options)
        if match := self._CHEESE_SS_URL.fullmatch(url):
            return CheeseSeasonSource(id=SeasonId(match.group("season_id")), options=options)
        return None


class UgcSeriesParser(Parser):
    _PLAYLIST_URL = re.compile(rf"{_BILIBILI}/list/(?P<mid>[0-9]+){_URL_END}", re.IGNORECASE)
    _SPACE_LIST_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+){_URL_END}", re.IGNORECASE
    )

    def parse(self, url: str, options: SourceOptions) -> UgcSeriesSource | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        if self._PLAYLIST_URL.fullmatch(url):
            sid = self._single_query_value(query, "sid")
            if sid is None:
                return None
            return UgcSeriesSource(id=SeriesId(sid), options=options)
        if match := self._SPACE_LIST_URL.fullmatch(url):
            if self._single_query_value(query, "type") != "series":
                return None
            return UgcSeriesSource(id=SeriesId(match.group("list_id")), options=options)
        return None


class UgcCollectionParser(Parser):
    _SPACE_LIST_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+){_URL_END}", re.IGNORECASE
    )
    _FAVOURITE_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE
    )

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        if match := self._SPACE_LIST_URL.fullmatch(url):
            if self._single_query_value(query, "type") != "season":
                return None
            return UgcCollectionSource(
                id=CollectionId(match.group("list_id")),
                owner_id=MId(match.group("mid")),
                options=options,
            )
        if match := self._FAVOURITE_URL.fullmatch(url):
            if self._single_query_value(query, "ftype") != "collect":
                return None
            fid = self._single_query_value(query, "fid")
            if fid is None:
                return None
            return UgcCollectionSource(
                id=CollectionId(fid),
                owner_id=MId(match.group("mid")),
                options=options,
            )
        return None


class UgcFavParser(Parser):
    _FAVOURITE_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE
    )

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        if not self._FAVOURITE_URL.fullmatch(url):
            return None
        if self._single_query_value(query, "ftype") == "collect":
            return None
        fid = self._single_query_value(query, "fid")
        if fid is None:
            return None
        return UgcFavSource(id=FId(fid), options=options)


class UgcWatchLaterParser(Parser):
    _WATCH_LATER_URL = re.compile(rf"{_BILIBILI}/(?:list/)?watchlater{_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        if self._WATCH_LATER_URL.fullmatch(url):
            return UgcWatchLaterSource(id=BilibiliId("watchlater"), options=options)
        return None


class UgcSpaceParser(Parser):
    _SPACE_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)(?:/video)?{_URL_END}", re.IGNORECASE
    )

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        if match := self._SPACE_URL.fullmatch(url):
            return UgcSpaceSource(id=MId(match.group("mid")), options=options)
        return None


class MixedParser(Parser):
    def parse(self, url: str, options: SourceOptions) -> Source | None:
        if match := _EP_ID.fullmatch(url):
            episode_id = EpisodeId(match.group("episode_id"))
            return AmbiguousSource(
                id=episode_id,
                options=options,
                candidates=(
                    BangumiEpisodeSource(id=episode_id, options=options),
                    CheeseEpisodeSource(id=episode_id, options=options),
                ),
            )
        if match := _SS_ID.fullmatch(url):
            season_id = SeasonId(match.group("season_id"))
            return AmbiguousSource(
                id=season_id,
                options=options,
                candidates=(
                    BangumiSeasonSource(id=season_id, options=options),
                    CheeseSeasonSource(id=season_id, options=options),
                ),
            )
        return None


def parse(value: str, options: SourceOptions | None = None) -> Source | None:
    value = value.strip()
    if not value:
        return None

    source_options = options if options is not None else SourceOptions()
    for parser in (
        UgcVideoParser(),
        BangumiParser(),
        CheeseParser(),
        UgcSeriesParser(),
        UgcCollectionParser(),
        UgcFavParser(),
        UgcWatchLaterParser(),
        UgcSpaceParser(),
        MixedParser(),
    ):
        source = parser.parse(value, source_options)
        if source is not None:
            return source
    return None
