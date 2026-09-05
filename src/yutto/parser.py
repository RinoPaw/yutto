from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    Options,
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


@dataclass(slots=True, kw_only=True)
class ParseOptions(Options):
    """Options used while turning one user input into its top-level Source."""

    selection: str | None = None
    source_options: SourceOptions = field(default_factory=SourceOptions)


class Parser(ABC):
    @abstractmethod
    def parse(self, url: str, options: ParseOptions) -> Source | None:
        raise NotImplementedError

    @staticmethod
    def _selection(options: ParseOptions, fallback: str = "1") -> str:
        return options.selection if options.selection is not None else fallback

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

    def parse(self, url: str, options: ParseOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)

        avid = self._parse_avid(url, query)
        if avid is None:
            return None

        selection = options.selection
        if selection is None:
            selection = self._parse_page(query)

        return UgcVideoSource(
            id=avid,
            selection=selection,
            options=options.source_options,
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

    def _parse_page(self, query: dict[str, list[str]]) -> str:
        page = self._single_query_value(query, "p")
        if page is None:
            return "1"
        try:
            int(page)
        except ValueError:
            raise WrongArgumentError(f"page `{page}` 不是整数") from None
        return page

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

    def parse(self, url: str, options: ParseOptions) -> BangumiEpisodeSource | BangumiSeasonSource | None:
        if match := self._BANGUMI_SS_URL.fullmatch(url):
            return BangumiSeasonSource(
                id=SeasonId(match.group("season_id")),
                selection=self._selection(options),
                options=options.source_options,
            )
        if match := self._BANGUMI_EP_URL.fullmatch(url):
            return BangumiEpisodeSource(
                id=EpisodeId(match.group("episode_id")),
                selection=options.selection,
                options=options.source_options,
            )
        if match := self._BANGUMI_MD_URL.fullmatch(url):
            return BangumiSeasonSource(
                id=MediaId(match.group("media_id")),
                selection=self._selection(options),
                options=options.source_options,
            )
        if match := self._B23_SS_URL.fullmatch(url):
            return BangumiSeasonSource(
                id=SeasonId(match.group("season_id")),
                selection=self._selection(options),
                options=options.source_options,
            )
        if match := self._B23_EP_URL.fullmatch(url):
            return BangumiEpisodeSource(
                id=EpisodeId(match.group("episode_id")),
                selection=options.selection,
                options=options.source_options,
            )
        if match := _MD_ID.fullmatch(url):
            return BangumiSeasonSource(
                id=MediaId(match.group("media_id")),
                selection=self._selection(options),
                options=options.source_options,
            )
        return None


class CheeseParser(Parser):
    _CHEESE_EP_URL = re.compile(
        r"https?://(?:www\.)?bilibili\.com/cheese/play/ep(?P<episode_id>[0-9]+)/?", re.IGNORECASE
    )
    _CHEESE_SS_URL = re.compile(
        r"https?://(?:www\.)?bilibili\.com/cheese/play/ss(?P<season_id>[0-9]+)/?", re.IGNORECASE
    )

    def parse(self, url: str, options: ParseOptions) -> CheeseEpisodeSource | CheeseSeasonSource | None:
        if match := self._CHEESE_EP_URL.fullmatch(url):
            return CheeseEpisodeSource(
                id=EpisodeId(match.group("episode_id")),
                selection=options.selection,
                options=options.source_options,
            )
        if match := self._CHEESE_SS_URL.fullmatch(url):
            return CheeseSeasonSource(
                id=SeasonId(match.group("season_id")),
                selection=self._selection(options),
                options=options.source_options,
            )
        return None


class UgcSeriesParser(Parser):
    _PLAYLIST_URL = re.compile(rf"{_BILIBILI}/list/(?P<mid>[0-9]+){_URL_END}", re.IGNORECASE)
    _SPACE_LIST_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+){_URL_END}", re.IGNORECASE
    )

    def parse(self, url: str, options: ParseOptions) -> UgcSeriesSource | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        selection = self._selection(options)
        if self._PLAYLIST_URL.fullmatch(url):
            sid = self._single_query_value(query, "sid")
            if sid is None:
                return None
            return UgcSeriesSource(id=SeriesId(sid), selection=selection, options=options.source_options)
        if match := self._SPACE_LIST_URL.fullmatch(url):
            if self._single_query_value(query, "type") != "series":
                return None
            return UgcSeriesSource(
                id=SeriesId(match.group("list_id")), selection=selection, options=options.source_options
            )
        return None


class UgcCollectionParser(Parser):
    _SPACE_LIST_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+){_URL_END}", re.IGNORECASE
    )
    _FAVOURITE_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE
    )

    def parse(self, url: str, options: ParseOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        selection = self._selection(options)
        if match := self._SPACE_LIST_URL.fullmatch(url):
            if self._single_query_value(query, "type") != "season":
                return None
            return UgcCollectionSource(
                id=CollectionId(match.group("list_id")),
                owner_id=MId(match.group("mid")),
                selection=selection,
                options=options.source_options,
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
                selection=selection,
                options=options.source_options,
            )
        return None


class UgcFavParser(Parser):
    _FAVOURITE_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE
    )

    def parse(self, url: str, options: ParseOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        if not self._FAVOURITE_URL.fullmatch(url):
            return None
        if self._single_query_value(query, "ftype") == "collect":
            return None
        fid = self._single_query_value(query, "fid")
        if fid is None:
            return None
        return UgcFavSource(id=FId(fid), selection=self._selection(options), options=options.source_options)


class UgcWatchLaterParser(Parser):
    _WATCH_LATER_URL = re.compile(rf"{_BILIBILI}/(?:list/)?watchlater{_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: ParseOptions) -> Source | None:
        if self._WATCH_LATER_URL.fullmatch(url):
            return UgcWatchLaterSource(
                id=BilibiliId("watchlater"),
                selection=self._selection(options),
                options=options.source_options,
            )
        return None


class UgcSpaceParser(Parser):
    _SPACE_URL = re.compile(
        rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)(?:/video)?{_URL_END}", re.IGNORECASE
    )

    def parse(self, url: str, options: ParseOptions) -> Source | None:
        if match := self._SPACE_URL.fullmatch(url):
            return UgcSpaceSource(
                id=MId(match.group("mid")),
                selection=self._selection(options),
                options=options.source_options,
            )
        return None


class MixedParser(Parser):
    def parse(self, url: str, options: ParseOptions) -> Source | None:
        source_options = options.source_options
        if match := _EP_ID.fullmatch(url):
            episode_id = EpisodeId(match.group("episode_id"))
            selection = options.selection
            return AmbiguousSource(
                id=episode_id,
                selection=selection,
                options=source_options,
                candidates=(
                    BangumiEpisodeSource(id=episode_id, selection=selection, options=source_options),
                    CheeseEpisodeSource(id=episode_id, selection=selection, options=source_options),
                ),
            )
        if match := _SS_ID.fullmatch(url):
            season_id = SeasonId(match.group("season_id"))
            selection = self._selection(options)
            return AmbiguousSource(
                id=season_id,
                selection=selection,
                options=source_options,
                candidates=(
                    BangumiSeasonSource(id=season_id, selection=selection, options=source_options),
                    CheeseSeasonSource(id=season_id, selection=selection, options=source_options),
                ),
            )
        return None


def parse(value: str, options: ParseOptions | SourceOptions | None = None) -> Source | None:
    value = value.strip()
    if not value:
        return None

    if options is None:
        parse_options = ParseOptions()
    elif isinstance(options, SourceOptions):
        parse_options = ParseOptions(source_options=options)
    else:
        parse_options = options

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
        source = parser.parse(value, parse_options)
        if source is not None:
            return source
    return None
