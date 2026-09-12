from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, TypeVar

from yutto.api.season import (
    get_bangumi_season,
    get_bangumi_season_by_episode,
    get_cheese_season,
    get_cheese_season_by_episode,
    get_season_id_by_media,
)
from yutto.api.ugc import (
    get_all_favourite_folders,
    get_collection,
    get_favourite_info,
    get_favourite_medias,
    get_series_archives,
    get_series_info,
    get_space_profile_and_archives,
    get_ugc_video_info,
    get_ugc_video_tags,
    get_watch_later_entries,
)
from yutto.core.operation import ReportLevel, emit_download_report
from yutto.exceptions import (
    HttpStatusError,
    MaxRetryError,
    NoAccessPermissionError,
    NotFoundError,
    NotLoginError,
    UnSupportedTypeError,
    WrongArgumentError,
)
from yutto.media import (
    BangumiEpisode,
    BangumiSeason,
    CheeseEpisode,
    CheeseSeason,
    Media,
    UgcAllFavourites,
    UgcCollection,
    UgcFav,
    UgcPage,
    UgcSeries,
    UgcSpace,
    UgcVideo,
    UgcWatchLater,
)
from yutto.selection import Range, Selection, parse_selection
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
from yutto.utils.filter import PublicationTimeFilter
from yutto.utils.metadata import Actor, ItemMetaData
from yutto.utils.time import get_time_stamp_by_now

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.core.request import DownloadRequest
    from yutto.exceptions import YuttoBaseException

T = TypeVar("T")

_EXPECTED_UGC_RESOLVE_ERRORS = (
    NotFoundError,
    NoAccessPermissionError,
    HttpStatusError,
    UnSupportedTypeError,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceOptions:
    selection: Selection | None = None
    with_extra_episodes: bool = False
    skip_preview: bool = False
    fetch_tags: bool = False
    publication_time_filter: PublicationTimeFilter | None = None

    @classmethod
    def from_request(cls, request: DownloadRequest) -> SourceOptions:
        expression = request.selection.expression
        publication_time_filter = None
        if request.selection.start_time is not None or request.selection.end_time is not None:
            publication_time_filter = PublicationTimeFilter.from_strings(
                request.selection.start_time,
                request.selection.end_time,
            )
        return cls(
            selection=parse_selection(expression) if expression is not None else None,
            with_extra_episodes=request.with_extra_episodes,
            skip_preview=request.selection.skip_preview,
            fetch_tags=request.resources.metadata,
            publication_time_filter=publication_time_filter,
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


@dataclass(frozen=True, slots=True)
class _FilteredUgcVideo:
    index: int
    source: AvId


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


async def _resolve_bangumi_or_cheese(
    bangumi: MediaSource,
    cheese: MediaSource,
    scope: ExecutionScope,
    options: SourceOptions,
) -> MediaResolveResult:
    results = await asyncio.gather(
        bangumi.resolve(scope, options),
        cheese.resolve(scope, options),
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
        raise WrongArgumentError("该 ID 同时存在于番剧和课程命名空间，无法自动判断")
    if successes:
        return successes[0]

    for failure in failures:
        if not isinstance(failure, NotFoundError):
            raise failure
    raise NotFoundError("未找到对应的番剧或课程内容")


class AmbiguousEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        return await _resolve_bangumi_or_cheese(
            BangumiEpisodeSource(id=self.id),
            CheeseEpisodeSource(id=self.id),
            scope,
            options,
        )


class AmbiguousSeasonSource(MediaSource):
    id: SeasonId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        return await _resolve_bangumi_or_cheese(
            BangumiSeasonSource(id=self.id),
            CheeseSeasonSource(id=self.id),
            scope,
            options,
        )


def bangumi_episode_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = list(result["episodes"])
    for section in result.get("section", []):
        if section["type"] != 5:
            items += section["episodes"]
    return items


def parse_bangumi_episode(index: int, item: dict[str, Any]) -> BangumiEpisode:
    long_title = item["long_title"]
    title = f"{item['title']} {long_title}" if long_title else item["title"]
    aid = AId(item["aid"]) if item.get("aid") is not None else BvId(item["bvid"]).as_aid()
    return BangumiEpisode(
        index=index,
        episode_id=EpisodeId(str(item["id"])),
        aid=aid,
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


def _resolve_selection_indexes(selection: Selection, total: int) -> tuple[int, ...]:
    result = selection.evaluate(total)
    if result.out_of_range:
        emit_download_report(
            "序号 {} 超出范围（1~{}），已忽略".format(",".join(map(str, result.out_of_range)), total),
            ReportLevel.WARNING,
        )
    if not result.indexes:
        message = "没有可供选择的项目" if total == 0 else "没有选中任何项目"
        emit_download_report(message, ReportLevel.WARNING)
    return result.indexes


class BangumiEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        result = await get_bangumi_season_by_episode(scope, self.id)

        all_episode_items = list(enumerate(bangumi_episode_items(result), start=1))
        anchor_item = next(
            ((index, entry) for index, entry in all_episode_items if entry["id"] == int(self.id.value)),
            None,
        )
        if anchor_item is None:
            raise NotFoundError(f"未找到该番剧中的剧集（episode_id: {self.id}）")

        season_metadata = make_bangumi_season_metadata(result)
        if options.selection is None:
            index, item = anchor_item
            episode = parse_bangumi_episode(index, item)
            _apply_container_metadata_to_episode(episode, season_metadata)
            return MediaResolveResult(media=episode)

        episode_items = indexed_bangumi_episode_items(result, with_extra_episodes=options.with_extra_episodes)
        if options.skip_preview:
            episode_items = [(index, item) for index, item in episode_items if item.get("badge") != "预告"]
        indexes = _resolve_selection_indexes(options.selection, len(episode_items))
        episode_items = [episode_items[index - 1] for index in indexes]
        return MediaResolveResult(
            media=BangumiSeason(
                season_id=SeasonId(str(result["season_id"])),
                metadata=season_metadata,
                items=[parse_bangumi_episode(index, item) for index, item in episode_items],
            )
        )


class BangumiSeasonSource(MediaSource):
    id: SeasonId | MediaId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        season_id = await get_season_id_by_media(scope, self.id) if isinstance(self.id, MediaId) else self.id
        result = await get_bangumi_season(scope, season_id)

        episode_items = indexed_bangumi_episode_items(result, with_extra_episodes=options.with_extra_episodes)
        if options.skip_preview:
            episode_items = [(index, item) for index, item in episode_items if item.get("badge") != "预告"]
        if options.selection is None:
            episode_items = episode_items[:1]
        else:
            indexes = _resolve_selection_indexes(options.selection, len(episode_items))
            episode_items = [episode_items[index - 1] for index in indexes]

        return MediaResolveResult(
            media=BangumiSeason(
                season_id=season_id,
                metadata=make_bangumi_season_metadata(result),
                items=[parse_bangumi_episode(index, item) for index, item in episode_items],
            )
        )


def parse_cheese_episode(index: int, item: dict[str, Any]) -> CheeseEpisode:
    title = item["title"]
    return CheeseEpisode(
        index=index,
        episode_id=EpisodeId(str(item["id"])),
        aid=AId(item["aid"]),
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
        result = await get_cheese_season_by_episode(scope, self.id)

        indexed_items = list(enumerate(result["episodes"], start=1))
        anchor_item = next(
            ((index, entry) for index, entry in indexed_items if entry["id"] == int(self.id.value)),
            None,
        )
        if anchor_item is None:
            raise NotFoundError(f"无法在课程 {result['title']} 中找到剧集 ep{self.id}")

        if options.selection is None:
            index, item = anchor_item
            return MediaResolveResult(media=parse_cheese_episode(index, item))

        indexes = _resolve_selection_indexes(options.selection, len(indexed_items))
        episode_items = [indexed_items[index - 1] for index in indexes]
        season_id = result.get("season_id", self.id.value)
        return MediaResolveResult(
            media=CheeseSeason(
                season_id=SeasonId(str(season_id)),
                metadata=ItemMetaData(title=str(result.get("title", ""))),
                items=[parse_cheese_episode(index, item) for index, item in episode_items],
            )
        )


class CheeseSeasonSource(MediaSource):
    id: SeasonId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        result = await get_cheese_season(scope, self.id)
        episode_items = list(enumerate(result["episodes"], start=1))
        if options.selection is None:
            episode_items = episode_items[:1]
        else:
            indexes = _resolve_selection_indexes(options.selection, len(episode_items))
            episode_items = [episode_items[index - 1] for index in indexes]

        return MediaResolveResult(
            media=CheeseSeason(
                season_id=self.id,
                metadata=ItemMetaData(title=str(result.get("title", ""))),
                items=[parse_cheese_episode(index, item) for index, item in episode_items],
            )
        )


@dataclass(slots=True, kw_only=True)
class UgcVideoSource(MediaSource):
    id: AvId
    page: int | None = None

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        try:
            return await self._resolve(scope, options)
        except _EXPECTED_UGC_RESOLVE_ERRORS as error:
            return MediaResolveResult(
                media=None,
                failures=(MediaResolveFailure(index=1, source=self.id, error=error),),
            )

    async def _resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        resolved_aid, video_info = await get_ugc_video_info(scope, self.id)
        tags = await get_ugc_video_tags(scope, resolved_aid) if options.fetch_tags else []
        dateadded = get_time_stamp_by_now()

        page_items: list[dict[str, Any]] = list(video_info["pages"])
        if options.selection is not None:
            indexes = _resolve_selection_indexes(options.selection, len(page_items))
        else:
            page = self.page if self.page is not None else 1
            if page > len(page_items):
                raise WrongArgumentError(f"序号 {page} 超出范围（1~{len(page_items)}）")
            indexes = (page,)

        pages = [
            UgcPage(
                aid=resolved_aid,
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
                aid=resolved_aid,
                page_count=len(page_items),
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


def _select_indexed(items: list[T], selection: Selection | None) -> list[tuple[int, T]]:
    indexed_items = list(enumerate(items, start=1))
    if selection is None:
        return indexed_items[:1]
    indexes = _resolve_selection_indexes(selection, len(indexed_items))
    return [indexed_items[index - 1] for index in indexes]


async def resolve_ugc_videos(
    scope: ExecutionScope,
    indexed_avids: list[tuple[int, AvId]],
    options: SourceOptions,
) -> tuple[tuple[_ResolvedUgcVideo, ...], tuple[MediaResolveFailure, ...]]:
    page_options = replace(options, selection=Selection((Range(None, None),)))
    results: list[_ResolvedUgcVideo | _FilteredUgcVideo | MediaResolveFailure | None] = [None] * len(indexed_avids)

    async def resolve_one(order: int, index: int, avid: AvId) -> None:
        try:
            result = await UgcVideoSource(id=avid).resolve(scope, page_options)
        except MaxRetryError as error:
            results[order] = MediaResolveFailure(index=index, source=avid, error=error)
            return

        if result.failures:
            if result.media is not None or len(result.failures) != 1:
                raise TypeError("UgcVideoSource returned an invalid failure result")
            results[order] = MediaResolveFailure(
                index=index,
                source=avid,
                error=result.failures[0].error,
            )
            return
        if not isinstance(result.media, UgcVideo):
            raise TypeError(f"UgcVideoSource returned unsupported media: {type(result.media).__name__}")

        publication_time_filter = options.publication_time_filter
        if publication_time_filter is not None and not publication_time_filter.matches(result.media.metadata.premiered):
            emit_download_report(
                f"因为发布时间为 {result.media.metadata.premiered}，跳过 {result.media.metadata.title}",
                ReportLevel.DEBUG,
            )
            results[order] = _FilteredUgcVideo(index=index, source=avid)
            return
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
        title, archives = await get_collection(scope, self.id, self.owner_id)
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
        info, medias = await asyncio.gather(
            get_favourite_info(scope, self.id),
            get_favourite_medias(scope, self.id),
        )
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


class UgcAllFavouritesSource(MediaSource):
    id: MId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        folders = await get_all_favourite_folders(scope, self.id)

        all_items_options = replace(options, selection=Selection((Range(None, None),)))
        favourites: list[UgcFav] = []
        failures: list[MediaResolveFailure] = []
        for folder in folders:
            fid = folder.get("id")
            if fid is None:
                continue
            result = await UgcFavSource(id=FId(str(fid))).resolve(scope, all_items_options)
            if not isinstance(result.media, UgcFav):
                raise TypeError("UgcFavSource returned unsupported media")
            favourites.append(result.media)
            failures.extend(result.failures)

        owner = next((favourite.metadata.owner for favourite in favourites if favourite.metadata.owner), "")
        return MediaResolveResult(
            media=UgcAllFavourites(
                mid=self.id,
                metadata=ItemMetaData(
                    title=f"{owner}的收藏夹" if owner else "用户收藏夹",
                    mid=self.id,
                    owner=owner,
                ),
                items=favourites,
            ),
            failures=tuple(failures),
        )


class UgcSeriesSource(MediaSource):
    id: SeriesId

    async def resolve(self, scope: ExecutionScope, options: SourceOptions) -> MediaResolveResult:
        info = await get_series_info(scope, self.id)
        meta = info.get("meta", {})
        mid = MId(str(meta["mid"]))
        archives = await get_series_archives(scope, self.id, mid)

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
        publication_time_filter = options.publication_time_filter
        profile, all_archives = await get_space_profile_and_archives(
            scope,
            self.id,
            stop_before_timestamp=(
                publication_time_filter.start_timestamp if publication_time_filter is not None else None
            ),
        )
        archives: list[dict[str, Any]] = []
        for item in all_archives:
            created = item.get("created")
            if publication_time_filter is None or created is None or publication_time_filter.matches(int(created)):
                archives.append(item)

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
        try:
            entries = await get_watch_later_entries(scope)
        except NotLoginError as error:
            return MediaResolveResult(
                media=None,
                failures=(MediaResolveFailure(index=1, source=self.id, error=error),),
            )

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
    "AmbiguousEpisodeSource",
    "AmbiguousSeasonSource",
    "BangumiEpisodeSource",
    "BangumiSeasonSource",
    "CheeseEpisodeSource",
    "CheeseSeasonSource",
    "MediaResolveFailure",
    "MediaResolveResult",
    "MediaSource",
    "SourceOptions",
    "UgcAllFavouritesSource",
    "UgcCollectionSource",
    "UgcFavSource",
    "UgcSeriesSource",
    "UgcSpaceSource",
    "UgcVideoSource",
    "UgcWatchLaterSource",
]
