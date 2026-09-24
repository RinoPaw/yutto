from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

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
from yutto.scope import Scope
from yutto.selection import Selection, parse_selection
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
from yutto.utils.metadata import Actor, ItemMetaData
from yutto.utils.time import get_time_stamp_by_now

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.exceptions import YuttoBaseException

T = TypeVar("T")
TMedia_co = TypeVar("TMedia_co", bound=Media, covariant=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaResolveStep:
    index: int
    source: BilibiliId


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaResolveFailure:
    path: tuple[MediaResolveStep, ...]
    error: YuttoBaseException

    def with_parent(self, *, index: int, source: BilibiliId) -> MediaResolveFailure:
        return MediaResolveFailure(
            path=(MediaResolveStep(index=index, source=source), *self.path),
            error=self.error,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaResolveResult(Generic[TMedia_co]):
    media: TMedia_co
    failures: tuple[MediaResolveFailure, ...] = ()


class MediaSource(ABC):
    @abstractmethod
    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult[Media]:
        raise NotImplementedError


def _publication_time_matches(timestamp: int, scope: Scope) -> bool:
    since = scope.selection.published_since
    before = scope.selection.published_before
    return (since is None or timestamp >= since) and (before is None or timestamp < before)


def _select_items(items: list[tuple[int, T]], selection: Selection) -> list[tuple[int, T]]:
    total = len(items)
    result = selection.evaluate(total)
    if result.out_of_range:
        emit_download_report(
            "序号 {} 超出范围（1~{}），已忽略".format(",".join(map(str, result.out_of_range)), total),
            ReportLevel.WARNING,
        )
    if not result.indexes:
        emit_download_report("没有可供选择的项目" if total == 0 else "没有选中任何项目", ReportLevel.WARNING)
    return [items[index - 1] for index in result.indexes]


_EXPECTED_UGC_CHILD_ERRORS = (
    NotFoundError,
    NoAccessPermissionError,
    HttpStatusError,
    UnSupportedTypeError,
    MaxRetryError,
)


@dataclass(slots=True, kw_only=True)
class UgcVideoSource(MediaSource):
    id: AvId
    page: int | None = None

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult[UgcVideo]:
        video_data = await get_ugc_video_info(execution, self.id)
        aid = AId(video_data["aid"])
        tags = await get_ugc_video_tags(execution, aid)
        added_at = get_time_stamp_by_now()
        page_data: list[dict[str, Any]] = list(video_data["pages"])
        selection_expression = scope.selection.expression
        selection = parse_selection(selection_expression) if selection_expression is not None else None
        if selection is not None:
            total = len(page_data)
            result = selection.evaluate(total)
            if result.out_of_range:
                emit_download_report(
                    "序号 {} 超出范围（1~{}），已忽略".format(",".join(map(str, result.out_of_range)), total),
                    ReportLevel.WARNING,
                )
            if not result.indexes:
                emit_download_report(
                    "没有可供选择的项目" if total == 0 else "没有选中任何项目",
                    ReportLevel.WARNING,
                )
            indexes = result.indexes
        else:
            page = self.page if self.page is not None else 1
            if page > len(page_data):
                raise WrongArgumentError(f"序号 {page} 超出范围（1~{len(page_data)}）")
            indexes = (page,)

        actors: list[Actor] = []
        if staff := video_data.get("staff"):
            actors = [
                Actor(
                    name=staff_info["name"],
                    role=staff_info["title"],
                    thumb=staff_info["face"],
                    profile=f"https://space.bilibili.com/{staff_info['mid']}",
                    order=index,
                )
                for index, staff_info in enumerate(staff)
            ]
        elif owner := video_data.get("owner"):
            actors = [
                Actor(
                    name=owner["name"],
                    role="UP主",
                    thumb=owner["face"],
                    profile=f"https://space.bilibili.com/{owner['mid']}",
                    order=0,
                )
            ]

        genre = video_data.get("tname")
        genres = [genre] if isinstance(genre, str) and genre else []

        def make_metadata(*, title: str, duration: int) -> ItemMetaData:
            owner_info = video_data.get("owner") or {}
            mid_value = owner_info.get("mid")
            return ItemMetaData(
                title=title,
                show_title=str(video_data.get("title", title)),
                plot=str(video_data.get("desc", "")),
                thumb=str(video_data.get("pic", "")),
                published_at=int(video_data.get("pubdate", 0)),
                duration=duration,
                mid=MId(str(mid_value)) if mid_value is not None else None,
                owner=str(owner_info.get("name", "")),
                added_at=added_at,
                actors=list(actors),
                genre=list(genres),
                tag=list(tags),
                website=BvId(video_data["bvid"]).to_url(),
            )

        pages = tuple(
            UgcPage(
                index=index,
                aid=aid,
                cid=CId(page_data[index - 1]["cid"]),
                metadata=make_metadata(
                    title=str(page_data[index - 1].get("part", video_data["title"])),
                    duration=int(page_data[index - 1].get("duration", 0)),
                ),
            )
            for index in indexes
        )
        return MediaResolveResult(
            media=UgcVideo(
                aid=aid,
                page_count=len(page_data),
                metadata=make_metadata(
                    title=str(video_data["title"]),
                    duration=int(video_data.get("duration", 0)),
                ),
                items=pages,
            )
        )


async def _resolve_ugc_videos(
    execution: ExecutionScope,
    indexed_avids: list[tuple[int, AvId]],
    video_scope: Scope,
) -> tuple[tuple[tuple[int, UgcVideo], ...], tuple[MediaResolveFailure, ...]]:
    async def resolve_one(index: int, avid: AvId) -> tuple[int, UgcVideo] | MediaResolveFailure | None:
        try:
            result = await UgcVideoSource(id=avid).resolve(execution, video_scope)
        except _EXPECTED_UGC_CHILD_ERRORS as error:
            return MediaResolveFailure(
                path=(MediaResolveStep(index=index, source=avid),),
                error=error,
            )

        if not _publication_time_matches(result.media.metadata.published_at, video_scope):
            emit_download_report(
                f"因为发布时间为 {result.media.metadata.published_at}，跳过 {result.media.metadata.title}",
                ReportLevel.DEBUG,
            )
            return None

        return index, result.media

    tasks: list[asyncio.Task[tuple[int, UgcVideo] | MediaResolveFailure | None]] = []
    try:
        async with asyncio.TaskGroup() as task_group:
            tasks = [task_group.create_task(resolve_one(index, avid)) for index, avid in indexed_avids]
    except ExceptionGroup as error_group:
        if len(error_group.exceptions) == 1:
            raise error_group.exceptions[0] from None
        raise

    resolved: list[tuple[int, UgcVideo]] = []
    failures: list[MediaResolveFailure] = []
    for task in tasks:
        result = task.result()
        if isinstance(result, MediaResolveFailure):
            failures.append(result)
        elif result is not None:
            resolved.append(result)
    return tuple(resolved), tuple(failures)


def _ugc_candidates(
    items: list[dict[str, Any]],
    scope: Scope,
    selection: Selection,
    *,
    publication_field: str,
) -> list[tuple[int, dict[str, Any]]]:
    indexed = list(enumerate(items, start=1))
    indexed = [
        (index, item)
        for index, item in indexed
        if item.get(publication_field) is None or _publication_time_matches(int(item[publication_field]), scope)
    ]
    return _select_items(indexed, selection)


@dataclass(slots=True, kw_only=True)
class UgcCollectionSource(MediaSource):
    id: CollectionId
    owner_id: MId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        title, archives = await get_collection(execution, self.id, self.owner_id)
        expression = scope.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_archives = _ugc_candidates(archives, scope, selection, publication_field="pubdate")
        video_scope = Scope({"selection.expression": "~"}, parent=scope)
        resolved, failures = await _resolve_ugc_videos(
            execution, [(index, BvId(item["bvid"])) for index, item in selected_archives], video_scope
        )
        return MediaResolveResult(
            media=UgcCollection(
                collection_id=self.id,
                metadata=ItemMetaData(title=title, mid=self.owner_id),
                items=tuple(video for _, video in resolved),
            ),
            failures=failures,
        )


@dataclass(slots=True, kw_only=True)
class UgcFavSource(MediaSource):
    id: FId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult[UgcFav]:
        info, medias = await asyncio.gather(
            get_favourite_info(execution, self.id),
            get_favourite_medias(execution, self.id),
        )
        expression = scope.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_medias = _ugc_candidates(medias, scope, selection, publication_field="pubtime")
        video_scope = Scope({"selection.expression": "~"}, parent=scope)
        resolved, failures = await _resolve_ugc_videos(
            execution, [(index, BvId(item["bvid"])) for index, item in selected_medias], video_scope
        )

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
                items=tuple(video for _, video in resolved),
            ),
            failures=failures,
        )


@dataclass(slots=True, kw_only=True)
class UgcAllFavouritesSource(MediaSource):
    id: MId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        folders = [
            folder for folder in await get_all_favourite_folders(execution, self.id) if folder.get("id") is not None
        ]
        expression = scope.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_folders = _select_items(list(enumerate(folders, start=1)), selection)
        child_scope = Scope({"selection.expression": "~"}, parent=scope)
        favourites: list[UgcFav] = []
        failures: list[MediaResolveFailure] = []

        for index, folder in selected_folders:
            fid = FId(str(folder["id"]))
            try:
                result = await UgcFavSource(id=fid).resolve(execution, child_scope)
            except _EXPECTED_UGC_CHILD_ERRORS as error:
                failures.append(
                    MediaResolveFailure(
                        path=(MediaResolveStep(index=index, source=fid),),
                        error=error,
                    )
                )
                continue
            favourites.append(result.media)
            failures.extend(failure.with_parent(index=index, source=fid) for failure in result.failures)

        owner = next((favourite.metadata.owner for favourite in favourites if favourite.metadata.owner), "")
        return MediaResolveResult(
            media=UgcAllFavourites(
                mid=self.id,
                metadata=ItemMetaData(
                    title=f"{owner}的收藏夹" if owner else "用户收藏夹",
                    mid=self.id,
                    owner=owner,
                ),
                items=tuple(favourites),
            ),
            failures=tuple(failures),
        )


@dataclass(slots=True, kw_only=True)
class UgcSeriesSource(MediaSource):
    id: SeriesId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        info = await get_series_info(execution, self.id)
        meta = info.get("meta", {})
        mid = MId(str(meta["mid"]))
        archives = await get_series_archives(execution, self.id, mid)
        expression = scope.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_archives = _ugc_candidates(archives, scope, selection, publication_field="pubdate")
        video_scope = Scope({"selection.expression": "~"}, parent=scope)
        resolved, failures = await _resolve_ugc_videos(
            execution, [(index, BvId(item["bvid"])) for index, item in selected_archives], video_scope
        )
        return MediaResolveResult(
            media=UgcSeries(
                series_id=self.id,
                metadata=ItemMetaData(
                    title=str(meta.get("name", "")),
                    mid=mid,
                    plot=str(meta.get("description", "")),
                ),
                items=tuple(video for _, video in resolved),
            ),
            failures=failures,
        )


@dataclass(slots=True, kw_only=True)
class UgcSpaceSource(MediaSource):
    id: MId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        profile, archives = await get_space_profile_and_archives(
            execution,
            self.id,
            stop_before_timestamp=scope.selection.published_since,
        )
        expression = scope.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_archives = _ugc_candidates(archives, scope, selection, publication_field="created")
        video_scope = Scope({"selection.expression": "~"}, parent=scope)
        resolved, failures = await _resolve_ugc_videos(
            execution, [(index, BvId(item["bvid"])) for index, item in selected_archives], video_scope
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
                items=tuple(video for _, video in resolved),
            ),
            failures=failures,
        )


@dataclass(slots=True, kw_only=True)
class UgcWatchLaterSource(MediaSource):
    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        entries = await get_watch_later_entries(execution)
        expression = scope.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_entries = _ugc_candidates(entries, scope, selection, publication_field="pubdate")
        video_scope = Scope({"selection.expression": "~"}, parent=scope)
        resolved, failures = await _resolve_ugc_videos(
            execution, [(index, BvId(item["bvid"])) for index, item in selected_entries], video_scope
        )
        return MediaResolveResult(
            media=UgcWatchLater(
                metadata=ItemMetaData(title="稍后再看"),
                items=tuple(video for _, video in resolved),
            ),
            failures=failures,
        )


def _bangumi_episode_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = list(result["episodes"])
    for section in result.get("section", []):
        if section["type"] != 5:
            items += section["episodes"]
    return items


def _parse_bangumi_episode(index: int, item: dict[str, Any]) -> BangumiEpisode:
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
            published_at=int(item.get("pub_time", 0)),
            duration=int(item.get("duration", 0)) // 1000,
            added_at=get_time_stamp_by_now(),
        ),
    )


def _make_bangumi_season_metadata(result: dict[str, Any]) -> ItemMetaData:
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


def _indexed_bangumi_episode_items(
    result: dict[str, Any],
    *,
    with_extra_episodes: bool,
) -> list[tuple[int, dict[str, Any]]]:
    all_items = _bangumi_episode_items(result)
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


@dataclass(slots=True, kw_only=True)
class BangumiEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        result = await get_bangumi_season_by_episode(execution, self.id)
        all_episode_items = list(enumerate(_bangumi_episode_items(result), start=1))
        anchor_item = next(
            ((index, entry) for index, entry in all_episode_items if entry["id"] == int(self.id.value)),
            None,
        )
        if anchor_item is None:
            raise NotFoundError(f"未找到该番剧中的剧集（episode_id: {self.id}）")

        season_metadata = _make_bangumi_season_metadata(result)
        expression = scope.selection.expression
        selection = parse_selection(expression) if expression is not None else None
        if selection is None:
            index, item = anchor_item
            episode = _parse_bangumi_episode(index, item)
            _apply_container_metadata_to_episode(episode, season_metadata)
            return MediaResolveResult(media=episode)

        episode_items = _indexed_bangumi_episode_items(
            result,
            with_extra_episodes=scope.selection.with_extra_episodes,
        )
        if scope.selection.skip_preview:
            episode_items = [(index, item) for index, item in episode_items if item.get("badge") != "预告"]
        episode_items = [
            (index, item)
            for index, item in episode_items
            if item.get("pub_time") is None or _publication_time_matches(int(item["pub_time"]), scope)
        ]
        episode_items = _select_items(episode_items, selection)
        return MediaResolveResult(
            media=BangumiSeason(
                season_id=SeasonId(str(result["season_id"])),
                metadata=season_metadata,
                items=tuple(_parse_bangumi_episode(index, item) for index, item in episode_items),
            )
        )


@dataclass(slots=True, kw_only=True)
class BangumiSeasonSource(MediaSource):
    id: SeasonId | MediaId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        season_id = await get_season_id_by_media(execution, self.id) if isinstance(self.id, MediaId) else self.id
        result = await get_bangumi_season(execution, season_id)
        episode_items = _indexed_bangumi_episode_items(
            result,
            with_extra_episodes=scope.selection.with_extra_episodes,
        )
        if scope.selection.skip_preview:
            episode_items = [(index, item) for index, item in episode_items if item.get("badge") != "预告"]
        episode_items = [
            (index, item)
            for index, item in episode_items
            if item.get("pub_time") is None or _publication_time_matches(int(item["pub_time"]), scope)
        ]
        expression = scope.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        episode_items = _select_items(episode_items, selection)
        return MediaResolveResult(
            media=BangumiSeason(
                season_id=season_id,
                metadata=_make_bangumi_season_metadata(result),
                items=tuple(_parse_bangumi_episode(index, item) for index, item in episode_items),
            )
        )


def _parse_cheese_episode(index: int, item: dict[str, Any]) -> CheeseEpisode:
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
            published_at=int(item.get("release_date", 0)),
            duration=int(item.get("duration", 0)),
            added_at=get_time_stamp_by_now(),
        ),
    )


def _cheese_episode_items(
    result: dict[str, Any],
    scope: Scope,
    selection: Selection,
) -> list[tuple[int, dict[str, Any]]]:
    items = [
        (index, item)
        for index, item in enumerate(result["episodes"], start=1)
        if item.get("release_date") is None or _publication_time_matches(int(item["release_date"]), scope)
    ]
    return _select_items(items, selection)


@dataclass(slots=True, kw_only=True)
class CheeseEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        result = await get_cheese_season_by_episode(execution, self.id)
        indexed_items = list(enumerate(result["episodes"], start=1))
        anchor_item = next(
            ((index, entry) for index, entry in indexed_items if entry["id"] == int(self.id.value)),
            None,
        )
        if anchor_item is None:
            raise NotFoundError(f"无法在课程 {result['title']} 中找到剧集 ep{self.id}")
        expression = scope.selection.expression
        if expression is None:
            index, item = anchor_item
            return MediaResolveResult(media=_parse_cheese_episode(index, item))
        selection = parse_selection(expression)
        episode_items = _cheese_episode_items(result, scope, selection)
        season_id = result.get("season_id", self.id.value)
        return MediaResolveResult(
            media=CheeseSeason(
                season_id=SeasonId(str(season_id)),
                metadata=ItemMetaData(title=str(result.get("title", ""))),
                items=tuple(_parse_cheese_episode(index, item) for index, item in episode_items),
            )
        )


@dataclass(slots=True, kw_only=True)
class CheeseSeasonSource(MediaSource):
    id: SeasonId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        result = await get_cheese_season(execution, self.id)
        expression = scope.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        episode_items = _cheese_episode_items(result, scope, selection)
        return MediaResolveResult(
            media=CheeseSeason(
                season_id=self.id,
                metadata=ItemMetaData(title=str(result.get("title", ""))),
                items=tuple(_parse_cheese_episode(index, item) for index, item in episode_items),
            )
        )


async def _resolve_bangumi_or_cheese(
    bangumi: MediaSource,
    cheese: MediaSource,
    execution: ExecutionScope,
    scope: Scope,
) -> MediaResolveResult:
    results = await asyncio.gather(
        bangumi.resolve(execution, scope),
        cheese.resolve(execution, scope),
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


@dataclass(slots=True, kw_only=True)
class AmbiguousEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        return await _resolve_bangumi_or_cheese(
            BangumiEpisodeSource(id=self.id),
            CheeseEpisodeSource(id=self.id),
            execution,
            scope,
        )


@dataclass(slots=True, kw_only=True)
class AmbiguousSeasonSource(MediaSource):
    id: SeasonId

    async def resolve(self, execution: ExecutionScope, scope: Scope) -> MediaResolveResult:
        return await _resolve_bangumi_or_cheese(
            BangumiSeasonSource(id=self.id),
            CheeseSeasonSource(id=self.id),
            execution,
            scope,
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
    "MediaResolveStep",
    "MediaSource",
    "UgcAllFavouritesSource",
    "UgcCollectionSource",
    "UgcFavSource",
    "UgcSeriesSource",
    "UgcSpaceSource",
    "UgcVideoSource",
    "UgcWatchLaterSource",
]
