from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, TypeVar

from returns.result import Failure

from yutto.auth import encode_wbi, get_wbi_img
from yutto.core.operation import ReportLevel, emit_download_report
from yutto.exceptions import (
    HttpStatusError,
    MaxRetryError,
    NoAccessPermissionError,
    NotFoundError,
    UnSupportedTypeError,
    WrongArgumentError,
)
from yutto.media import (
    BangumiEpisode,
    BangumiSeason,
    CheeseEpisode,
    CheeseSeason,
    Media,
    UgcCollection,
    UgcFav,
    UgcPage,
    UgcSeries,
    UgcSpace,
    UgcVideo,
    UgcWatchLater,
)
from yutto.selection import Range, Selection
from yutto.types import (
    AId,
    AvId,
    BilibiliId,
    BvId,
    CId,
    CollectionId,
    EpisodeId,
    FId,
    MediaId,
    MId,
    SeasonId,
    SeriesId,
)
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.metadata import Actor, ItemMetaData
from yutto.utils.time import get_time_stamp_by_now

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.core.options import SourceOptions
    from yutto.exceptions import YuttoBaseException

T = TypeVar("T")

_EXPECTED_CHILD_RESOLVE_ERRORS = (
    NotFoundError,
    NoAccessPermissionError,
    MaxRetryError,
    HttpStatusError,
    UnSupportedTypeError,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaResolveFailure:
    index: int
    source: BilibiliId
    error: YuttoBaseException


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaResolveResult:
    media: Media | None
    failures: tuple[MediaResolveFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class _ResolvedUgcVideo:
    index: int
    source: AvId
    media: UgcVideo


@dataclass(slots=True, kw_only=True)
class MediaSource(ABC):
    id: BilibiliId

    @abstractmethod
    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        raise NotImplementedError

    @staticmethod
    def _parse_actors_info(video_info: dict[str, Any]) -> list[Actor]:
        if staff := video_info.get("staff"):
            return [
                Actor(
                    name=staff_info["name"],
                    role=staff_info["title"],
                    thumb=staff_info["face"],
                    profile=f"https://space.bilibili.com/{staff_info['mid']}",
                    order=index,
                )
                for index, staff_info in enumerate(staff)
            ]

        if owner := video_info.get("owner"):
            return [
                Actor(
                    name=owner["name"],
                    role="UP主",
                    thumb=owner["face"],
                    profile=f"https://space.bilibili.com/{owner['mid']}",
                    order=0,
                )
            ]

        emit_download_report("未找到演员信息", ReportLevel.WARNING)
        return []

    @staticmethod
    def _parse_genre_info(video_info: dict[str, Any]) -> list[str]:
        genre = video_info.get("tname")
        return [genre] if isinstance(genre, str) and genre else []

    @staticmethod
    async def _fetch_payload(
        scope: ExecutionScope,
        url: str,
        description: str,
        identifier: str,
        data_key: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if params is None:
            result = await Fetcher.fetch_json(scope, url)
        else:
            result = await Fetcher.fetch_json(scope, url, params=params)
        response = unwrap_fetch_result(result)
        if response.get("code") == -404:
            raise NotFoundError(f"未找到{description}（{identifier}）")
        payload = response.get(data_key)
        if payload is None:
            raise NoAccessPermissionError(f"无法解析{description}（{identifier}），原因：{response.get('message')}")
        return payload


@dataclass(slots=True, kw_only=True)
class AmbiguousSource(MediaSource):
    candidates: tuple[MediaSource, ...]

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        results = await asyncio.gather(
            *(candidate.resolve(scope, options) for candidate in self.candidates),
            return_exceptions=True,
        )
        successes: list[MediaResolveResult] = []
        failures: list[BaseException] = []
        for result in results:
            if isinstance(result, BaseException):
                failures.append(result)
            else:
                successes.append(result)

        if len(successes) > 1:
            raise WrongArgumentError("该 ID 同时存在于多个命名空间，无法自动判断")
        if successes:
            return successes[0]

        for failure in failures:
            if not isinstance(failure, NotFoundError):
                raise failure
        raise NotFoundError("未找到对应的内容")


def bangumi_episode_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = list(result["episodes"])
    for section in result.get("section", []):
        if section["type"] != 5:
            items += section["episodes"]
    return items


def parse_bangumi_episode(index: int, item: dict[str, Any]) -> BangumiEpisode:
    long_title = item["long_title"]
    title = f"{item['title']} {long_title}" if long_title else item["title"]
    return BangumiEpisode(
        index=index,
        episode_id=EpisodeId(str(item["id"])),
        avid=BvId(item["bvid"]),
        cid=CId(item["cid"]),
        is_preview=item.get("badge") == "预告",
        metadata=ItemMetaData(
            title=title,
            show_title=item.get("share_copy", title),
            plot=item.get("share_copy", ""),
            thumb=item.get("cover", ""),
            premiered=int(item.get("pub_time", 0)),
            duration=int(item.get("duration", 0)) // 1000,
            dateadded=get_time_stamp_by_now(),
        ),
    )


def make_bangumi_season_metadata(result: dict[str, Any]) -> ItemMetaData:
    up_info = result.get("up_info") or {}
    mid_value = up_info.get("mid")
    mid = MId(str(mid_value)) if mid_value is not None else None
    owner = str(up_info.get("uname", ""))
    actors: list[Actor] = []
    if owner:
        actors.append(
            Actor(
                name=owner,
                role="UP主",
                thumb=str(up_info.get("avatar", "")),
                profile=f"https://space.bilibili.com/{mid}" if mid is not None else "",
                order=0,
            )
        )
    return ItemMetaData(
        title=str(result.get("title", "")),
        plot=str(result.get("evaluate", "")),
        mid=mid,
        owner=owner,
        genre=list(result.get("styles") or []),
        actors=actors,
    )


def indexed_bangumi_episode_items(
    result: dict[str, Any],
    *,
    with_extra_episodes: bool,
) -> list[tuple[int, dict[str, Any]]]:
    all_items = bangumi_episode_items(result)
    indexed_items = list(enumerate(all_items, start=1))
    if with_extra_episodes:
        return indexed_items
    return indexed_items[: len(result["episodes"])]


def _apply_container_metadata_to_episode(episode: BangumiEpisode, metadata: ItemMetaData) -> None:
    episode.metadata.mid = episode.metadata.mid or metadata.mid
    episode.metadata.owner = episode.metadata.owner or metadata.owner
    if not episode.metadata.genre:
        episode.metadata.genre = list(metadata.genre)
    if not episode.metadata.actors:
        episode.metadata.actors = list(metadata.actors)


class BangumiEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        api = f"https://api.bilibili.com/pgc/view/web/season?ep_id={self.id}"
        res = await self._fetch_payload(scope, api, "该番剧", f"episode_id: {self.id}", "result")

        all_episode_items = list(enumerate(bangumi_episode_items(res), start=1))
        anchor_item = next(
            ((index, entry) for index, entry in all_episode_items if entry["id"] == int(self.id.value)),
            None,
        )
        if anchor_item is None:
            raise NotFoundError(f"未找到该番剧中的剧集（episode_id: {self.id}）")

        season_metadata = make_bangumi_season_metadata(res)
        if options.selection is None:
            index, item = anchor_item
            episode = parse_bangumi_episode(index, item)
            _apply_container_metadata_to_episode(episode, season_metadata)
            return MediaResolveResult(media=episode)

        episode_items = indexed_bangumi_episode_items(res, with_extra_episodes=options.with_extra_episodes)
        if options.skip_preview:
            episode_items = [(index, item) for index, item in episode_items if item.get("badge") != "预告"]
        indexes = options.selection.resolve(len(episode_items))
        episode_items = [episode_items[index - 1] for index in indexes]
        return MediaResolveResult(
            media=BangumiSeason(
                season_id=SeasonId(str(res["season_id"])),
                metadata=season_metadata,
                items=[parse_bangumi_episode(index, item) for index, item in episode_items],
            )
        )


class BangumiSeasonSource(MediaSource):
    id: SeasonId | MediaId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        season_id = await self._get_season_id(scope, self.id) if isinstance(self.id, MediaId) else self.id
        api = f"https://api.bilibili.com/pgc/view/web/season?season_id={season_id}"
        res = await self._fetch_payload(scope, api, "该番剧列表", f"season_id: {season_id}", "result")

        episode_items = indexed_bangumi_episode_items(res, with_extra_episodes=options.with_extra_episodes)
        if options.skip_preview:
            episode_items = [(index, item) for index, item in episode_items if item.get("badge") != "预告"]
        if options.selection is None:
            episode_items = episode_items[:1]
        else:
            indexes = options.selection.resolve(len(episode_items))
            episode_items = [episode_items[index - 1] for index in indexes]

        return MediaResolveResult(
            media=BangumiSeason(
                season_id=season_id,
                metadata=make_bangumi_season_metadata(res),
                items=[parse_bangumi_episode(index, item) for index, item in episode_items],
            )
        )

    @staticmethod
    async def _get_season_id(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
        media_api = f"https://api.bilibili.com/pgc/review/user?media_id={media_id}"
        res_json = unwrap_fetch_result(await Fetcher.fetch_json(scope, media_api))
        return SeasonId(str(res_json["result"]["media"]["season_id"]))


def parse_cheese_episode(index: int, item: dict[str, Any]) -> CheeseEpisode:
    title = item["title"]
    return CheeseEpisode(
        index=index,
        episode_id=EpisodeId(str(item["id"])),
        avid=AId(item["aid"]),
        cid=CId(item["cid"]),
        metadata=ItemMetaData(
            title=title,
            show_title=title,
            plot=title,
            thumb=item.get("cover", ""),
            premiered=int(item.get("release_date", 0)),
            duration=int(item.get("duration", 0)),
            dateadded=get_time_stamp_by_now(),
        ),
    )


class CheeseEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        api = f"https://api.bilibili.com/pugv/view/web/season?ep_id={self.id}"
        res = await self._fetch_payload(scope, api, "该课程", f"episode_id: {self.id}", "data")

        indexed_items = list(enumerate(res["episodes"], start=1))
        anchor_item = next(
            ((index, entry) for index, entry in indexed_items if entry["id"] == int(self.id.value)),
            None,
        )
        if anchor_item is None:
            raise NotFoundError(f"无法在课程 {res['title']} 中找到剧集 ep{self.id}")

        if options.selection is None:
            index, item = anchor_item
            return MediaResolveResult(media=parse_cheese_episode(index, item))

        indexes = options.selection.resolve(len(indexed_items))
        episode_items = [indexed_items[index - 1] for index in indexes]
        season_id = res.get("season_id", self.id.value)
        return MediaResolveResult(
            media=CheeseSeason(
                season_id=SeasonId(str(season_id)),
                metadata=ItemMetaData(title=str(res.get("title", ""))),
                items=[parse_cheese_episode(index, item) for index, item in episode_items],
            )
        )


class CheeseSeasonSource(MediaSource):
    id: SeasonId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        api = f"https://api.bilibili.com/pugv/view/web/season?season_id={self.id}"
        res = await self._fetch_payload(scope, api, "该课程列表", f"season_id: {self.id}", "data")
        episode_items = list(enumerate(res["episodes"], start=1))
        if options.selection is None:
            episode_items = episode_items[:1]
        else:
            indexes = options.selection.resolve(len(episode_items))
            episode_items = [episode_items[index - 1] for index in indexes]

        return MediaResolveResult(
            media=CheeseSeason(
                season_id=self.id,
                metadata=ItemMetaData(title=str(res.get("title", ""))),
                items=[parse_cheese_episode(index, item) for index, item in episode_items],
            )
        )


@dataclass(slots=True, kw_only=True)
class UgcVideoSource(MediaSource):
    id: AvId
    page: int | None = None

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        resolved_avid, video_info = await self.get_ugc_video_info(scope, self.id)
        tags = await self.get_ugc_video_tag(scope, resolved_avid) if options.fetch_tags else []
        dateadded = get_time_stamp_by_now()

        page_items: list[dict[str, Any]] = list(video_info["pages"])
        if options.selection is not None:
            indexes = options.selection.resolve(len(page_items))
        else:
            page = self.page if self.page is not None else 1
            if page > len(page_items):
                raise WrongArgumentError(f"序号 {page} 超出范围（1~{len(page_items)}）")
            indexes = (page,)

        pages = [
            UgcPage(
                avid=resolved_avid,
                page=index,
                cid=CId(page_items[index - 1]["cid"]),
                metadata=self._make_ugc_metadata(
                    video_info,
                    tags,
                    dateadded,
                    title=str(page_items[index - 1].get("part", video_info["title"])),
                    duration=int(page_items[index - 1].get("duration", 0)),
                ),
            )
            for index in indexes
        ]
        return MediaResolveResult(
            media=UgcVideo(
                avid=resolved_avid,
                metadata=self._make_ugc_metadata(
                    video_info,
                    tags,
                    dateadded,
                    title=str(video_info["title"]),
                    duration=int(video_info.get("duration", 0)),
                ),
                items=pages,
            )
        )

    def _make_ugc_metadata(
        self,
        video_info: dict[str, Any],
        tags: list[str],
        dateadded: int,
        *,
        title: str,
        duration: int,
    ) -> ItemMetaData:
        owner_info = video_info.get("owner") or {}
        mid_value = owner_info.get("mid")
        return ItemMetaData(
            title=title,
            show_title=str(video_info.get("title", title)),
            plot=str(video_info.get("desc", "")),
            thumb=str(video_info.get("pic", "")),
            premiered=int(video_info.get("pubdate", 0)),
            duration=duration,
            mid=MId(str(mid_value)) if mid_value is not None else None,
            owner=str(owner_info.get("name", "")),
            dateadded=dateadded,
            actors=self._parse_actors_info(video_info),
            genre=self._parse_genre_info(video_info),
            tag=list(tags),
            website=BvId(video_info["bvid"]).to_url(),
        )

    async def get_ugc_video_info(
        self,
        scope: ExecutionScope,
        avid: AvId,
    ) -> tuple[AvId, dict[str, Any]]:
        api = f"https://api.bilibili.com/x/web-interface/view?{avid.to_param()}"
        res = await Fetcher.fetch_json(scope, api)
        if isinstance(res, Failure):
            raise NotFoundError(f"无法获取该视频 {avid} 信息") from res.failure()

        res_json = res.unwrap()
        res_json_data = res_json.get("data")
        if res_json["code"] == 62002:
            raise NotFoundError(f"无法下载该视频 {avid}，原因：{res_json['message']}")
        if res_json["code"] == 62012:
            raise NoAccessPermissionError(
                f"无法获取该视频 {avid} 信息，原因：{res_json['message']}（当前稿件UP主设置为仅自己可见）"
            )
        if res_json["code"] == -404:
            raise NotFoundError(f"哔咔！视频 {avid} 不见了诶")
        assert res_json_data is not None, "响应数据无 data 域"

        if res_json_data.get("forward"):
            forward_avid = AId(res_json_data["forward"])
            emit_download_report(f"视频 {avid} 撞车了哦！正在跳转到原视频 {forward_avid}～")
            return await self.get_ugc_video_info(scope, forward_avid)

        return avid, res_json_data

    async def get_ugc_video_tag(self, scope: ExecutionScope, avid: AvId) -> list[str]:
        api = f"https://api.bilibili.com/x/tag/archive/tags?{avid.to_param()}"
        res_json = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
        if res_json["code"] != 0:
            raise NotFoundError(f"无法获取视频 {avid} 标签")
        return [tag["tag_name"] for tag in res_json["data"]]


def _select_indexed(items: list[T], selection: Selection | None) -> list[tuple[int, T]]:
    indexed_items = list(enumerate(items, start=1))
    if selection is None:
        return indexed_items[:1]
    indexes = selection.resolve(len(indexed_items))
    return [indexed_items[index - 1] for index in indexes]


async def resolve_ugc_videos(
    scope: ExecutionScope,
    indexed_avids: list[tuple[int, AvId]],
    options: SourceOptions,
) -> tuple[tuple[_ResolvedUgcVideo, ...], tuple[MediaResolveFailure, ...]]:
    page_options = replace(options, selection=Selection((Range(None, None),)))
    results: list[_ResolvedUgcVideo | MediaResolveFailure | None] = [None] * len(indexed_avids)

    async def resolve_one(order: int, index: int, avid: AvId) -> None:
        try:
            result = await UgcVideoSource(id=avid).resolve(scope, page_options)
        except _EXPECTED_CHILD_RESOLVE_ERRORS as error:
            results[order] = MediaResolveFailure(index=index, source=avid, error=error)
            return

        if result.failures:
            raise TypeError("UgcVideoSource must not return nested resolve failures")
        if not isinstance(result.media, UgcVideo):
            raise TypeError(f"UgcVideoSource returned unsupported media: {type(result.media).__name__}")
        results[order] = _ResolvedUgcVideo(index=index, source=avid, media=result.media)

    try:
        async with asyncio.TaskGroup() as task_group:
            for order, (index, avid) in enumerate(indexed_avids):
                task_group.create_task(resolve_one(order, index, avid))
    except ExceptionGroup as error_group:
        if len(error_group.exceptions) == 1:
            raise error_group.exceptions[0] from None
        raise

    completed = [result for result in results if result is not None]
    if len(completed) != len(indexed_avids):
        raise RuntimeError("UGC batch resolve completed without a result for every child")
    return (
        tuple(result for result in completed if isinstance(result, _ResolvedUgcVideo)),
        tuple(result for result in completed if isinstance(result, MediaResolveFailure)),
    )


@dataclass(slots=True, kw_only=True)
class UgcCollectionSource(MediaSource):
    id: CollectionId
    owner_id: MId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        page_size = 30
        page_num = 1
        archives: list[dict[str, Any]] = []
        title = ""

        while True:
            list_api = (
                "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
                f"?mid={self.owner_id}&season_id={self.id}&sort_reverse=false"
                f"&page_num={page_num}&page_size={page_size}"
            )
            payload = await self._fetch_payload(
                scope,
                list_api,
                "视频合集",
                f"collection_id: {self.id}",
                "data",
            )
            if page_num == 1:
                title = payload.get("meta", {}).get("name", "")

            page_archives: list[dict[str, Any]] = payload.get("archives") or []
            archives.extend(item for item in page_archives if item.get("bvid"))

            total = payload.get("page", {}).get("total")
            if isinstance(total, int):
                if page_num * page_size >= total:
                    break
            elif len(page_archives) < page_size:
                break
            page_num += 1

        selected_archives = _select_indexed(archives, options.selection)
        resolved, failures = await resolve_ugc_videos(
            scope,
            [(index, BvId(item["bvid"])) for index, item in selected_archives],
            options,
        )
        return MediaResolveResult(
            media=UgcCollection(
                collection_id=self.id,
                metadata=ItemMetaData(title=title, mid=self.owner_id),
                items=[item.media for item in resolved],
            ),
            failures=failures,
        )


class UgcFavSource(MediaSource):
    id: FId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        info_api = f"https://api.bilibili.com/x/v3/fav/folder/info?media_id={self.id}"
        info = await self._fetch_payload(scope, info_api, "收藏夹", f"fid: {self.id}", "data")

        page_size = 20
        page_num = 1
        medias: list[dict[str, Any]] = []
        while True:
            list_api = (
                f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={self.id}"
                f"&pn={page_num}&ps={page_size}&platform=web"
            )
            payload = await self._fetch_payload(scope, list_api, "收藏夹", f"fid: {self.id}", "data")
            page_medias: list[dict[str, Any]] = payload.get("medias") or []
            medias.extend(item for item in page_medias if item.get("bvid"))

            has_more = payload.get("has_more")
            if has_more is not None:
                if not has_more:
                    break
            elif len(page_medias) < page_size:
                break
            page_num += 1

        selected_medias = _select_indexed(medias, options.selection)
        resolved, failures = await resolve_ugc_videos(
            scope,
            [(index, BvId(item["bvid"])) for index, item in selected_medias],
            options,
        )
        for resolved_video in resolved:
            favourite = medias[resolved_video.index - 1]
            video = resolved_video.media
            favourite_title = str(favourite.get("title") or video.metadata.title)
            video.metadata.title = favourite_title
            if len(video.items) == 1:
                video.items[0].metadata.title = favourite_title
                video.items[0].metadata.show_title = favourite_title

        upper = info.get("upper") or {}
        upper_mid = upper.get("mid")
        return MediaResolveResult(
            media=UgcFav(
                fid=self.id,
                metadata=ItemMetaData(
                    title=str(info.get("title", "")),
                    plot=str(info.get("intro", "")),
                    thumb=str(info.get("cover", "")),
                    mid=MId(str(upper_mid)) if upper_mid is not None else None,
                    owner=str(upper.get("name", "")),
                ),
                items=[item.media for item in resolved],
            ),
            failures=failures,
        )


class UgcSeriesSource(MediaSource):
    id: SeriesId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        info_api = f"https://api.bilibili.com/x/series/series?series_id={self.id}"
        info = await self._fetch_payload(scope, info_api, "视频系列", f"series_id: {self.id}", "data")
        meta = info.get("meta", {})
        mid = MId(str(meta["mid"]))

        page_size = 30
        page_num = 1
        archives: list[dict[str, Any]] = []
        while True:
            list_api = (
                "https://api.bilibili.com/x/series/archives"
                f"?mid={mid}&series_id={self.id}&only_normal=true"
                f"&pn={page_num}&ps={page_size}"
            )
            payload = await self._fetch_payload(scope, list_api, "视频系列", f"series_id: {self.id}", "data")
            page_archives: list[dict[str, Any]] = payload.get("archives") or []
            archives.extend(item for item in page_archives if item.get("bvid"))

            total = payload.get("page", {}).get("total")
            if isinstance(total, int):
                if page_num * page_size >= total:
                    break
            elif len(page_archives) < page_size:
                break
            page_num += 1

        selected_archives = _select_indexed(archives, options.selection)
        resolved, failures = await resolve_ugc_videos(
            scope,
            [(index, BvId(item["bvid"])) for index, item in selected_archives],
            options,
        )
        return MediaResolveResult(
            media=UgcSeries(
                series_id=self.id,
                metadata=ItemMetaData(
                    title=str(meta.get("name", "")),
                    mid=mid,
                    plot=str(meta.get("description", "")),
                ),
                items=[item.media for item in resolved],
            ),
            failures=failures,
        )


class UgcSpaceSource(MediaSource):
    id: MId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        wbi_img = await get_wbi_img(scope)
        profile = await self._fetch_payload(
            scope,
            "https://api.bilibili.com/x/space/wbi/acc/info",
            "UP 主",
            f"mid: {self.id}",
            "data",
            params=encode_wbi({"mid": self.id}, wbi_img),
        )

        page_size = 30
        page_num = 1
        archives: list[dict[str, Any]] = []
        while True:
            payload = await self._fetch_payload(
                scope,
                "https://api.bilibili.com/x/space/wbi/arc/search",
                "UP 主空间",
                f"mid: {self.id}",
                "data",
                params=encode_wbi(
                    {
                        "mid": self.id,
                        "ps": page_size,
                        "tid": 0,
                        "pn": page_num,
                        "order": "pubdate",
                    },
                    wbi_img,
                ),
            )
            page_archives: list[dict[str, Any]] = payload.get("list", {}).get("vlist") or []
            archives.extend(item for item in page_archives if item.get("bvid"))

            total = payload.get("page", {}).get("count")
            if isinstance(total, int):
                if page_num * page_size >= total:
                    break
            elif len(page_archives) < page_size:
                break
            page_num += 1

        selected_archives = _select_indexed(archives, options.selection)
        resolved, failures = await resolve_ugc_videos(
            scope,
            [(index, BvId(item["bvid"])) for index, item in selected_archives],
            options,
        )
        return MediaResolveResult(
            media=UgcSpace(
                mid=self.id,
                metadata=ItemMetaData(
                    title=str(profile.get("name", "")),
                    plot=str(profile.get("sign", "")),
                    thumb=str(profile.get("face", "")),
                    mid=self.id,
                    owner=str(profile.get("name", "")),
                ),
                items=[item.media for item in resolved],
            ),
            failures=failures,
        )


class UgcWatchLaterSource(MediaSource):
    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        payload = await self._fetch_payload(
            scope,
            "https://api.bilibili.com/x/v2/history/toview/web",
            "稍后再看",
            "watch_later",
            "data",
        )
        entries: list[dict[str, Any]] = [item for item in payload.get("list", []) if item.get("bvid")]
        selected_entries = _select_indexed(entries, options.selection)
        resolved, failures = await resolve_ugc_videos(
            scope,
            [(index, BvId(item["bvid"])) for index, item in selected_entries],
            options,
        )
        return MediaResolveResult(
            media=UgcWatchLater(
                metadata=ItemMetaData(title="稍后再看"),
                items=[item.media for item in resolved],
            ),
            failures=failures,
        )


__all__ = [
    "AmbiguousSource",
    "BangumiEpisodeSource",
    "BangumiSeasonSource",
    "CheeseEpisodeSource",
    "CheeseSeasonSource",
    "MediaResolveFailure",
    "MediaResolveResult",
    "MediaSource",
    "UgcCollectionSource",
    "UgcFavSource",
    "UgcSeriesSource",
    "UgcSpaceSource",
    "UgcVideoSource",
    "UgcWatchLaterSource",
]
