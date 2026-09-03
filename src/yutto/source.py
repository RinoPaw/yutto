from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from yutto.api.bangumi import get_season_id_by_episode_id as get_bangumi_season_id_by_episode_id
from yutto.api.cheese import get_season_id_by_episode_id as get_cheese_season_id_by_episode_id
from yutto.container import Collection, Favourite, Series, UserFavourites, UserVideos, WatchLater
from yutto.exceptions import EpisodeNotFoundError, WrongArgumentError
from yutto.media import (
    BangumiEpisode,
    BangumiMedia,
    BangumiSeason,
    CheeseEpisode,
    CheeseSeason,
    UgcPage,
    UgcVideo,
)
from yutto.types import AId, BvId, EpisodeId, FId, MediaId, MId, SeasonId, SeriesId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


Container = WatchLater | UserVideos | Favourite | UserFavourites | Series | Collection
Item = UgcVideo | BangumiMedia | BangumiSeason | CheeseSeason
Child = UgcPage | BangumiEpisode | CheeseEpisode


@dataclass(frozen=True, slots=True)
class Source:
    """用户输入中携带的来源上下文与当前焦点。"""

    container: Container | None = None
    current_item: Item | None = None
    current_child: Child | None = None

    # 用户直接输入 ID
    _AV_ID = re.compile(r"av(?P<aid>[0-9]+)", re.IGNORECASE)
    _BV_ID = re.compile(r"(?P<bvid>BV[A-Za-z0-9]+)", re.IGNORECASE)
    _EP_ID = re.compile(r"ep(?P<episode_id>[0-9]+)", re.IGNORECASE)
    _SS_ID = re.compile(r"ss(?P<season_id>[0-9]+)", re.IGNORECASE)
    _MD_ID = re.compile(r"md(?P<media_id>[0-9]+)", re.IGNORECASE)

    _BILIBILI = r"https?://(?:www\.)?bilibili\.com"
    _SPACE_BILIBILI = r"https?://space\.bilibili\.com"
    _URL_END = r"/?(?=[?#]|$)"

    # 用户输入 URL
    _UGC_AV_URL = re.compile(rf"{_BILIBILI}/video/av(?P<aid>[0-9]+){_URL_END}", re.IGNORECASE)
    _UGC_BV_URL = re.compile(rf"{_BILIBILI}/video/(?P<bvid>BV[A-Za-z0-9]+){_URL_END}", re.IGNORECASE)
    _FESTIVAL_URL = re.compile(rf"{_BILIBILI}/festival/", re.IGNORECASE)
    _BANGUMI_EP_URL = re.compile(rf"{_BILIBILI}/bangumi/play/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _BANGUMI_SS_URL = re.compile(rf"{_BILIBILI}/bangumi/play/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _BANGUMI_MD_URL = re.compile(rf"{_BILIBILI}/bangumi/media/md(?P<media_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _CHEESE_EP_URL = re.compile(rf"{_BILIBILI}/cheese/play/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _CHEESE_SS_URL = re.compile(rf"{_BILIBILI}/cheese/play/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _WATCH_LATER_URL = re.compile(rf"{_BILIBILI}/(?:list/)?watchlater{_URL_END}", re.IGNORECASE)
    _SERIES_PLAYLIST_URL = re.compile(rf"{_BILIBILI}/list/(?P<mid>[0-9]+){_URL_END}", re.IGNORECASE)
    _SPACE_LIST_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _FAVOURITE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE)
    _USER_SPACE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)(?:/video)?{_URL_END}", re.IGNORECASE)

    def __post_init__(self) -> None:
        if self.container is None and self.current_item is None and self.current_child is None:
            raise ValueError("Source must contain at least one target")

    @classmethod
    async def parse(cls, scope: ExecutionScope, value: str) -> Source | None:
        """解析用户输入并创建对应的领域对象。"""

        value = value.strip()
        if not value:
            return None

        if parsed := await cls._parse_url(scope, value):
            return parsed
        return await cls._parse_id(scope, value)

    @classmethod
    async def _parse_url(cls, scope: ExecutionScope, value: str) -> Source | None:
        parsed = urlparse(value)
        query = parse_qs(parsed.query, keep_blank_values=True)

        if cls._WATCH_LATER_URL.match(value):
            container = await WatchLater.create(scope)
            current_item = await cls._ugc_item_from_query(scope, query)
            return Source(
                container=container,
                current_item=current_item,
                current_child=cls._ugc_page_from_query(current_item, query) if current_item is not None else None,
            )

        if match := cls._SERIES_PLAYLIST_URL.match(value):
            series_id = cls._single_query_value(query, "sid")
            if series_id is not None and not (series_id.isascii() and series_id.isdigit()):
                raise WrongArgumentError(f"无效的 sid 参数（sid: {series_id}）")
            if series_id is not None:
                container = await Series.create(
                    scope,
                    MId(match.group("mid")),
                    SeriesId(series_id),
                )
                current_item = await cls._ugc_item_from_query(scope, query)
                return Source(
                    container=container,
                    current_item=current_item,
                    current_child=cls._ugc_page_from_query(current_item, query) if current_item is not None else None,
                )

        if match := cls._SPACE_LIST_URL.match(value):
            mid = MId(match.group("mid"))
            list_id = match.group("list_id")
            list_type = cls._single_query_value(query, "type")
            if list_type is not None and list_type not in ("season", "series"):
                raise WrongArgumentError(f"无效的 type 参数（type: {list_type}）")

            if list_type == "season":
                container = await Collection.create(scope, mid, SeasonId(list_id))
                current_item = await cls._ugc_item_from_query(scope, query)
                return Source(
                    container=container,
                    current_item=current_item,
                    current_child=cls._ugc_page_from_query(current_item, query) if current_item is not None else None,
                )

            if list_type == "series":
                container = await Series.create(scope, mid, SeriesId(list_id))
                current_item = await cls._ugc_item_from_query(scope, query)
                return Source(
                    container=container,
                    current_item=current_item,
                    current_child=cls._ugc_page_from_query(current_item, query) if current_item is not None else None,
                )

            return None

        if match := cls._FAVOURITE_URL.match(value):
            mid = MId(match.group("mid"))
            fid = cls._single_query_value(query, "fid")
            favourite_type = cls._single_query_value(query, "ftype")

            container: Container
            if fid is None:
                container = await UserFavourites.create(scope, mid)
            elif not (fid.isascii() and fid.isdigit()):
                raise WrongArgumentError(f"无效的 fid 参数（fid: {fid}）")
            elif favourite_type == "collect":
                container = await Collection.create(scope, mid, SeasonId(fid))
            else:
                container = await Favourite.create(scope, mid, FId(fid))

            current_item = await cls._ugc_item_from_query(scope, query)
            return Source(
                container=container,
                current_item=current_item,
                current_child=cls._ugc_page_from_query(current_item, query) if current_item is not None else None,
            )

        if match := cls._USER_SPACE_URL.match(value):
            container = await UserVideos.create(scope, MId(match.group("mid")))
            return Source(container=container)

        return None
