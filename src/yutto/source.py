from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from returns.result import Failure

from yutto.api.user_info import encode_wbi, get_wbi_img
from yutto.core.operation import ReportLevel, emit_download_report
from yutto.core.options import SourceOptions
from yutto.exceptions import NoAccessPermissionError, NotFoundError, WrongArgumentError
from yutto.media import (
    BangumiEpisode,
    BangumiSeason,
    CheeseEpisode,
    CheeseSeason,
    MediaContainer,
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
    MId,
    MediaId,
    SeasonId,
    SeriesId,
)
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.metadata import Actor, ItemMetaData
from yutto.utils.time import get_time_stamp_by_now

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class Source(ABC):
    id: BilibiliId

    @abstractmethod
    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaContainer:
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

        emit_download_report("未找到演职人员信息", ReportLevel.WARNING)
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
class AmbiguousSource(Source):
    candidates: tuple[Source, ...]

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaContainer:
        results = await asyncio.gather(
            *(candidate.resolve(scope, options) for candidate in self.candidates),
            return_exceptions=True,
        )
        successes = [result for result in results if not isinstance(result, BaseException)]
        if len(successes) > 1:
            raise WrongArgumentError("该 ID 同时存在于多个命名空间，无法自动判断")
        if successes:
            return successes[0]

        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, NotFoundError):
                raise result
        raise NotFoundError("未找到对应的内容")


def bangumi_episode_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = list(result["episodes"])
    for section in result.get("section", []):
        if section["type"] != 5:
            items += section["episodes"]
    return items


def parse_bangumi_episode(item: dict[str, Any]) -> BangumiEpisode:
    long_title = item["long_title"]
    title = f"{item['title']} {long_title}" if long_title else item["title"]
    return BangumiEpisode(
        episode_id=EpisodeId(str(item["id"])),
        avid=BvId(item["bvid"]),
        cid=CId(item["cid"]),
        metadata=ItemMetaData(
            title=title,
            show_title=item.get("share_copy", title),
            plot=item.get("share_copy", ""),
            thumb=item.get("cover", ""),
            premiered=int(item.get("pub_time", 0)),
            duration=int(item.get("duration", 0)) // 1000,
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


class BangumiEpisodeSource(Source):
    id: EpisodeId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> BangumiSeason:
        api = f"https://api.bilibili.com/pgc/view/web/season?ep_id={self.id}"
        res = await self._fetch_payload(scope, api, "该番剧", f"episode_id: {self.id}", "result")

        all_episode_items = bangumi_episode_items(res)
        anchor_item = next((entry for entry in all_episode_items if entry["id"] == int(self.id.value)), None)
        if anchor_item is None:
            raise NotFoundError(f"未找到该番剧中的剧集（episode_id: {self.id}）")

        if options.selection is None:
            episode_items = [anchor_item]
        else:
            episode_items: list[dict[str, Any]] = list(res["episodes"])
            if options.with_extra_episodes:
                for section in res.get("section", []):
                    if section["type"] != 5:
                        episode_items.extend(section["episodes"])
            if options.skip_preview:
                episode_items = [item for item in episode_items if item.get("badge") != "预告"]
            indexes = options.selection.resolve(len(episode_items))
            episode_items = [episode_items[index - 1] for index in indexes]

        return BangumiSeason(
            season_id=SeasonId(str(res["season_id"])),
            metadata=make_bangumi_season_metadata(res),
            items=[parse_bangumi_episode(item) for item in episode_items],
        )


class BangumiSeasonSource(Source):
    id: SeasonId | MediaId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> BangumiSeason:
        season_id = await self._get_season_id(scope, self.id) if isinstance(self.id, MediaId) else self.id
        api = f"https://api.bilibili.com/pgc/view/web/season?season_id={season_id}"
        res = await self._fetch_payload(scope, api, "该番剧列表", f"season_id: {season_id}", "result")

        episode_items: list[dict[str, Any]] = list(res["episodes"])
        if options.with_extra_episodes:
            for section in res.get("section", []):
                if section["type"] != 5:
                    episode_items.extend(section["episodes"])
        if options.skip_preview:
            episode_items = [item for item in episode_items if item.get("badge") != "预告"]
        if options.selection is None:
            episode_items = episode_items[:1]
        else:
            indexes = options.selection.resolve(len(episode_items))
            episode_items = [episode_items[index - 1] for index in indexes]

        return BangumiSeason(
            season_id=season_id,
            metadata=make_bangumi_season_metadata(res),
            items=[parse_bangumi_episode(item) for item in episode_items],
        )

    @staticmethod
    async def _get_season_id(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
        media_api = f"https://api.bilibili.com/pgc/review/user?media_id={media_id}"
        res_json = unwrap_fetch_result(await Fetcher.fetch_json(scope, media_api))
        return SeasonId(str(res_json["result"]["media"]["season_id"]))


def parse_cheese_episode(item: dict[str, Any]) -> CheeseEpisode:
    title = item["title"]
    return CheeseEpisode(
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
        ),
    )


class CheeseEpisodeSource(Source):
    id: EpisodeId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> CheeseSeason:
        api = f"https://api.bilibili.com/pugv/view/web/season?ep_id={self.id}"
        res = await self._fetch_payload(scope, api, "该课程", f"episode_id: {self.id}", "data")

        anchor_item = next((entry for entry in res["episodes"] if entry["id"] == int(self.id.value)), None)
        if anchor_item is None:
            raise NotFoundError(f"无法在课程 {res['title']} 中找到剧集 ep{self.id}")

        if options.selection is None:
            episode_items = [anchor_item]
        else:
            indexes = options.selection.resolve(len(res["episodes"]))
            episode_items = [res["episodes"][index - 1] for index in indexes]
        season_id = res.get("season_id", self.id.value)
        return CheeseSeason(
            season_id=SeasonId(str(season_id)),
            metadata=ItemMetaData(title=str(res.get("title", ""))),
            items=[parse_cheese_episode(item) for item in episode_items],
        )


class CheeseSeasonSource(Source):
    id: SeasonId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> CheeseSeason:
        api = f"https://api.bilibili.com/pugv/view/web/season?season_id={self.id}"
        res = await self._fetch_payload(scope, api, "该课程列表", f"season_id: {self.id}", "data")
        episode_items: list[dict[str, Any]] = list(res["episodes"])
        if options.selection is None:
            episode_items = episode_items[:1]
        else:
            indexes = options.selection.resolve(len(episode_items))
            episode_items = [episode_items[index - 1] for index in indexes]

        return CheeseSeason(
            season_id=self.id,
            metadata=ItemMetaData(title=str(res.get("title", ""))),
            items=[parse_cheese_episode(item) for item in episode_items],
        )


@dataclass(slots=True, kw_only=True)
class UgcVideoSource(Source):
    id: AvId
    page: int | None = None

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> UgcVideo:
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
                cid=CId(item["cid"]),
                metadata=self._make_ugc_metadata(
                    video_info,
                    tags,
                    dateadded,
                    title=str(item.get("part", video_info["title"])),
                    duration=int(item.get("duration", 0)),
                ),
            )
            for item in (page_items[index - 1] for index in indexes)
        ]
        return UgcVideo(
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
                f"无法获取该视频 {avid} 信息，原因：{res_json['message']}（当前稿件up主设置为仅自见）"
            )
        if res_json["code"] == -404:
            raise NotFoundError(f"啊叻？视频 {avid} 不见了诶")
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


async def resolve_ugc_videos(
    scope: ExecutionScope,
    avids: list[AvId],
    options: SourceOptions,
) -> list[UgcVideo]:
    page_options = replace(options, selection=Selection((Range(None, None),)))
    return list(
        await asyncio.gather(
            *(UgcVideoSource(id=avid).resolve(scope, page_options) for avid in avids)
        )
    )


@dataclass(slots=True, kw_only=True)
class UgcCollectionSource(Source):
    id: CollectionId
    owner_id: MId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> UgcCollection:
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

        if options.selection is None:
            selected_archives = archives[:1]
        else:
            indexes = options.selection.resolve(len(archives))
            selected_archives = [archives[index - 1] for index in indexes]
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_archives],
            options,
        )
        return UgcCollection(
            collection_id=self.id,
            metadata=ItemMetaData(title=title, mid=self.owner_id),
            items=videos,
        )


class UgcFavSource(Source):
    id: FId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> UgcFav:
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

        if options.selection is None:
            selected_medias = medias[:1]
        else:
            indexes = options.selection.resolve(len(medias))
            selected_medias = [medias[index - 1] for index in indexes]
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_medias],
            options,
        )
        return UgcFav(
            fid=self.id,
            metadata=ItemMetaData(
                title=str(info.get("title", "")),
                plot=str(info.get("intro", "")),
                thumb=str(info.get("cover", "")),
            ),
            items=videos,
        )


class UgcSeriesSource(Source):
    id: SeriesId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> UgcSeries:
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

        if options.selection is None:
            selected_archives = archives[:1]
        else:
            indexes = options.selection.resolve(len(archives))
            selected_archives = [archives[index - 1] for index in indexes]
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_archives],
            options,
        )
        return UgcSeries(
            series_id=self.id,
            metadata=ItemMetaData(
                title=str(meta.get("name", "")),
                mid=mid,
                plot=str(meta.get("description", "")),
            ),
            items=videos,
        )


class UgcSpaceSource(Source):
    id: MId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> UgcSpace:
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

        if options.selection is None:
            selected_archives = archives[:1]
        else:
            indexes = options.selection.resolve(len(archives))
            selected_archives = [archives[index - 1] for index in indexes]
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_archives],
            options,
        )
        return UgcSpace(
            mid=self.id,
            metadata=ItemMetaData(
                title=str(profile.get("name", "")),
                plot=str(profile.get("sign", "")),
                thumb=str(profile.get("face", "")),
                mid=self.id,
                owner=str(profile.get("name", "")),
            ),
            items=videos,
        )


class UgcWatchLaterSource(Source):
    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> UgcWatchLater:
        payload = await self._fetch_payload(
            scope,
            "https://api.bilibili.com/x/v2/history/toview/web",
            "稍后再看",
            "watch_later",
            "data",
        )
        entries: list[dict[str, Any]] = [item for item in payload.get("list", []) if item.get("bvid")]
        if options.selection is None:
            selected_entries = entries[:1]
        else:
            indexes = options.selection.resolve(len(entries))
            selected_entries = [entries[index - 1] for index in indexes]
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_entries],
            options,
        )
        return UgcWatchLater(metadata=ItemMetaData(title="稍后再看"), items=videos)


__all__ = [
    "AmbiguousSource",
    "BangumiEpisodeSource",
    "BangumiSeasonSource",
    "CheeseEpisodeSource",
    "CheeseSeasonSource",
    "Source",
    "UgcCollectionSource",
    "UgcFavSource",
    "UgcSeriesSource",
    "UgcSpaceSource",
    "UgcVideoSource",
    "UgcWatchLaterSource",
]
