from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Generic, TypeVar

from yutto.api.season import (
    BangumiEpisodeInfo,
    BangumiSeasonInfo,
    CheeseEpisodeInfo,
    CheeseSeasonInfo,
    get_bangumi_season,
    get_bangumi_season_by_episode,
    get_cheese_season,
    get_cheese_season_by_episode,
    get_season_id_by_media,
)
from yutto.api.ugc import (
    UgcVideoReference,
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
from yutto.config import ResolvedConfig
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
    MediaEntry,
    UgcAllFavourites,
    UgcCollection,
    UgcFav,
    UgcPage,
    UgcSeries,
    UgcSpace,
    UgcVideo,
    UgcWatchLater,
)
from yutto.selection import Selection, parse_selection
from yutto.types import (
    AvId,
    BilibiliId,
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
class MediaResolveDiagnostic:
    """Structured selection facts produced while resolving a media source."""

    total: int
    out_of_range: tuple[int, ...] = ()
    empty: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaResolveResult(Generic[TMedia_co]):
    media: TMedia_co
    source_index: int | None = None
    failures: tuple[MediaResolveFailure, ...] = ()
    diagnostics: tuple[MediaResolveDiagnostic, ...] = ()


class MediaSource(ABC):
    @abstractmethod
    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult[Media]:
        raise NotImplementedError


def _publication_time_matches(timestamp: int, config: ResolvedConfig) -> bool:
    since = config.selection.published_since
    before = config.selection.published_before
    return (since is None or timestamp >= since) and (before is None or timestamp < before)


def _select_items(
    items: list[tuple[int, T]],
    selection: Selection,
    diagnostics: list[MediaResolveDiagnostic],
) -> list[tuple[int, T]]:
    total = len(items)
    result = selection.evaluate(total)
    if result.out_of_range or not result.indexes:
        diagnostics.append(
            MediaResolveDiagnostic(
                total=total,
                out_of_range=tuple(result.out_of_range),
                empty=not result.indexes,
            )
        )
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

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult[UgcVideo]:
        video_info = await get_ugc_video_info(execution, self.id)
        aid = video_info.aid
        tags = await get_ugc_video_tags(execution, aid)
        added_at = get_time_stamp_by_now()
        pages = video_info.pages
        diagnostics: list[MediaResolveDiagnostic] = []
        selection_expression = config.selection.expression
        selection = parse_selection(selection_expression) if selection_expression is not None else None
        if selection is not None:
            selected_pages = _select_items(list(enumerate(pages, start=1)), selection, diagnostics)
            indexes = tuple(index for index, _ in selected_pages)
        else:
            page = self.page if self.page is not None else 1
            if page > len(pages):
                raise WrongArgumentError(f"序号 {page} 超出范围（1~{len(pages)}）")
            indexes = (page,)

        actors: list[Actor] = []
        if video_info.staff:
            actors = [
                Actor(
                    name=staff_info.name,
                    role=staff_info.role,
                    thumb=staff_info.face,
                    profile=f"https://space.bilibili.com/{staff_info.mid}",
                    order=index,
                )
                for index, staff_info in enumerate(video_info.staff)
            ]
        elif video_info.owner is not None:
            owner = video_info.owner
            actors = [
                Actor(
                    name=owner.name,
                    role="UP主",
                    thumb=owner.face,
                    profile=f"https://space.bilibili.com/{owner.mid}" if owner.mid is not None else "",
                    order=0,
                )
            ]

        genres = [video_info.category] if video_info.category else []

        def make_metadata(*, title: str, duration: int) -> ItemMetaData:
            owner = video_info.owner
            return ItemMetaData(
                title=title,
                show_title=video_info.title,
                plot=video_info.description,
                thumb=video_info.cover,
                published_at=video_info.published_at,
                duration=duration,
                mid=owner.mid if owner is not None else None,
                owner=owner.name if owner is not None else "",
                added_at=added_at,
                actors=actors,
                genre=genres,
                tag=tags,
                website=video_info.bvid.to_url(),
            )

        page_items = tuple(
            MediaEntry(
                index=index,
                media=UgcPage(
                    aid=aid,
                    cid=pages[index - 1].cid,
                    metadata=make_metadata(
                        title=pages[index - 1].title,
                        duration=pages[index - 1].duration,
                    ),
                ),
            )
            for index in indexes
        )
        return MediaResolveResult(
            media=UgcVideo(
                aid=aid,
                page_count=len(pages),
                metadata=make_metadata(
                    title=video_info.title,
                    duration=video_info.duration,
                ),
                items=page_items,
            ),
            diagnostics=tuple(diagnostics),
        )


async def _resolve_ugc_videos(
    execution: ExecutionScope,
    indexed_videos: list[tuple[int, UgcVideoReference]],
    video_config: ResolvedConfig,
) -> tuple[tuple[MediaEntry[UgcVideo], ...], tuple[MediaResolveFailure, ...], tuple[MediaResolveDiagnostic, ...]]:
    async def resolve_one(
        index: int,
        reference: UgcVideoReference,
    ) -> tuple[MediaEntry[UgcVideo], tuple[MediaResolveDiagnostic, ...]] | MediaResolveFailure | None:
        try:
            result = await UgcVideoSource(id=reference.bvid).resolve(execution, video_config)
        except _EXPECTED_UGC_CHILD_ERRORS as error:
            return MediaResolveFailure(
                path=(MediaResolveStep(index=index, source=reference.bvid),),
                error=error,
            )

        if not _publication_time_matches(result.media.metadata.published_at, video_config):
            return None

        return (
            MediaEntry(index=index, media=result.media, display_title=reference.title),
            result.diagnostics,
        )

    tasks: list[
        asyncio.Task[tuple[MediaEntry[UgcVideo], tuple[MediaResolveDiagnostic, ...]] | MediaResolveFailure | None]
    ] = []
    try:
        async with asyncio.TaskGroup() as task_group:
            tasks = [task_group.create_task(resolve_one(index, reference)) for index, reference in indexed_videos]
    except ExceptionGroup as error_group:
        if len(error_group.exceptions) == 1:
            raise error_group.exceptions[0] from None
        raise

    resolved: list[MediaEntry[UgcVideo]] = []
    failures: list[MediaResolveFailure] = []
    diagnostics: list[MediaResolveDiagnostic] = []
    for task in tasks:
        result = task.result()
        if isinstance(result, MediaResolveFailure):
            failures.append(result)
        elif result is not None:
            entry, child_diagnostics = result
            resolved.append(entry)
            diagnostics.extend(child_diagnostics)
    return tuple(resolved), tuple(failures), tuple(diagnostics)


def _ugc_candidates(
    items: tuple[UgcVideoReference, ...],
    config: ResolvedConfig,
    selection: Selection,
    diagnostics: list[MediaResolveDiagnostic],
) -> list[tuple[int, UgcVideoReference]]:
    indexed = list(enumerate(items, start=1))
    indexed = [
        (index, item)
        for index, item in indexed
        if item.published_at is None or _publication_time_matches(item.published_at, config)
    ]
    return _select_items(indexed, selection, diagnostics)


def _with_all_selected(config: ResolvedConfig) -> ResolvedConfig:
    return replace(config, selection=replace(config.selection, expression="~"))


@dataclass(slots=True, kw_only=True)
class UgcCollectionSource(MediaSource):
    id: CollectionId
    owner_id: MId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        collection = await get_collection(execution, self.id, self.owner_id)
        diagnostics: list[MediaResolveDiagnostic] = []
        expression = config.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_videos = _ugc_candidates(collection.videos, config, selection, diagnostics)
        video_config = _with_all_selected(config)
        resolved, failures, child_diagnostics = await _resolve_ugc_videos(execution, selected_videos, video_config)
        diagnostics.extend(child_diagnostics)
        return MediaResolveResult(
            media=UgcCollection(
                collection_id=self.id,
                metadata=ItemMetaData(title=collection.title, mid=self.owner_id),
                items=resolved,
            ),
            failures=failures,
            diagnostics=tuple(diagnostics),
        )


@dataclass(slots=True, kw_only=True)
class UgcFavSource(MediaSource):
    id: FId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult[UgcFav]:
        info, videos = await asyncio.gather(
            get_favourite_info(execution, self.id),
            get_favourite_medias(execution, self.id),
        )
        diagnostics: list[MediaResolveDiagnostic] = []
        expression = config.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_videos = _ugc_candidates(videos, config, selection, diagnostics)
        video_config = _with_all_selected(config)
        resolved, failures, child_diagnostics = await _resolve_ugc_videos(execution, selected_videos, video_config)
        diagnostics.extend(child_diagnostics)

        owner = info.owner
        return MediaResolveResult(
            media=UgcFav(
                fid=self.id,
                metadata=ItemMetaData(
                    title=info.title,
                    plot=info.description,
                    thumb=info.cover,
                    mid=owner.mid if owner is not None else None,
                    owner=owner.name if owner is not None else "",
                ),
                items=resolved,
            ),
            failures=failures,
            diagnostics=tuple(diagnostics),
        )


@dataclass(slots=True, kw_only=True)
class UgcAllFavouritesSource(MediaSource):
    id: MId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        folders = await get_all_favourite_folders(execution, self.id)
        diagnostics: list[MediaResolveDiagnostic] = []
        expression = config.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_folders = _select_items(list(enumerate(folders, start=1)), selection, diagnostics)
        child_config = _with_all_selected(config)
        favourites: list[MediaEntry[UgcFav]] = []
        failures: list[MediaResolveFailure] = []

        for index, fid in selected_folders:
            try:
                result = await UgcFavSource(id=fid).resolve(execution, child_config)
            except _EXPECTED_UGC_CHILD_ERRORS as error:
                failures.append(
                    MediaResolveFailure(
                        path=(MediaResolveStep(index=index, source=fid),),
                        error=error,
                    )
                )
                continue
            favourites.append(MediaEntry(index=index, media=result.media))
            failures.extend(failure.with_parent(index=index, source=fid) for failure in result.failures)
            diagnostics.extend(result.diagnostics)

        owner = next((entry.media.metadata.owner for entry in favourites if entry.media.metadata.owner), "")
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
            diagnostics=tuple(diagnostics),
        )


@dataclass(slots=True, kw_only=True)
class UgcSeriesSource(MediaSource):
    id: SeriesId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        info = await get_series_info(execution, self.id)
        archives = await get_series_archives(execution, self.id, info.owner_id)
        diagnostics: list[MediaResolveDiagnostic] = []
        expression = config.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_videos = _ugc_candidates(archives, config, selection, diagnostics)
        video_config = _with_all_selected(config)
        resolved, failures, child_diagnostics = await _resolve_ugc_videos(execution, selected_videos, video_config)
        diagnostics.extend(child_diagnostics)
        return MediaResolveResult(
            media=UgcSeries(
                series_id=self.id,
                metadata=ItemMetaData(title=info.title, mid=info.owner_id, plot=info.description),
                items=resolved,
            ),
            failures=failures,
            diagnostics=tuple(diagnostics),
        )


@dataclass(slots=True, kw_only=True)
class UgcSpaceSource(MediaSource):
    id: MId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        profile, archives = await get_space_profile_and_archives(
            execution,
            self.id,
            stop_before_timestamp=config.selection.published_since,
        )
        diagnostics: list[MediaResolveDiagnostic] = []
        expression = config.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_videos = _ugc_candidates(archives, config, selection, diagnostics)
        video_config = _with_all_selected(config)
        resolved, failures, child_diagnostics = await _resolve_ugc_videos(execution, selected_videos, video_config)
        diagnostics.extend(child_diagnostics)
        return MediaResolveResult(
            media=UgcSpace(
                mid=self.id,
                metadata=ItemMetaData(
                    title=profile.name,
                    plot=profile.description,
                    thumb=profile.face,
                    mid=self.id,
                    owner=profile.name,
                ),
                items=resolved,
            ),
            failures=failures,
            diagnostics=tuple(diagnostics),
        )


@dataclass(slots=True, kw_only=True)
class UgcWatchLaterSource(MediaSource):
    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        entries = await get_watch_later_entries(execution)
        diagnostics: list[MediaResolveDiagnostic] = []
        expression = config.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        selected_videos = _ugc_candidates(entries, config, selection, diagnostics)
        video_config = _with_all_selected(config)
        resolved, failures, child_diagnostics = await _resolve_ugc_videos(execution, selected_videos, video_config)
        diagnostics.extend(child_diagnostics)
        return MediaResolveResult(
            media=UgcWatchLater(metadata=ItemMetaData(title="稍后再看", items=resolved)),
            failures=failures,
            diagnostics=tuple(diagnostics),
        )


def _parse_bangumi_episode(item: BangumiEpisodeInfo) -> BangumiEpisode:
    return BangumiEpisode(
        episode_id=item.episode_id,
        aid=item.aid,
        cid=item.cid,
        is_preview=item.is_preview,
        metadata=ItemMetaData(
            title=item.title,
            show_title=item.show_title,
            plot=item.show_title,
            thumb=item.cover,
            published_at=item.published_at or 0,
            duration=item.duration,
            added_at=get_time_stamp_by_now(),
        ),
    )


def _make_bangumi_season_metadata(result: BangumiSeasonInfo) -> ItemMetaData:
    owner = result.owner
    actors: list[Actor] = []
    if owner is not None and owner.name:
        actors.append(
            Actor(
                name=owner.name,
                role="UP主",
                thumb=owner.avatar,
                profile=f"https://space.bilibili.com/{owner.mid}" if owner.mid is not None else "",
                order=0,
            )
        )
    return ItemMetaData(
        title=result.title,
        plot=result.description,
        mid=owner.mid if owner is not None else None,
        owner=owner.name if owner is not None else "",
        genre=result.genres,
        actors=actors,
    )


def _indexed_bangumi_episode_items(
    result: BangumiSeasonInfo,
    *,
    with_extra_episodes: bool,
) -> list[tuple[int, BangumiEpisodeInfo]]:
    items = result.episodes if with_extra_episodes else result.episodes[: result.main_episode_count]
    return list(enumerate(items, start=1))


def _apply_container_metadata_to_episode(episode: BangumiEpisode, metadata: ItemMetaData) -> BangumiEpisode:
    episode_metadata = episode.metadata
    return replace(
        episode,
        metadata=replace(
            episode_metadata,
            mid=episode_metadata.mid or metadata.mid,
            owner=episode_metadata.owner or metadata.owner,
            genre=episode_metadata.genre or metadata.genre,
            actors=episode_metadata.actors or metadata.actors,
        ),
    )


@dataclass(slots=True, kw_only=True)
class BangumiEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        result = await get_bangumi_season_by_episode(execution, self.id)
        all_episode_items = list(enumerate(result.episodes, start=1))
        anchor_item = next(((index, entry) for index, entry in all_episode_items if entry.episode_id == self.id), None)
        if anchor_item is None:
            raise NotFoundError(f"未找到该番剧中的剧集（episode_id: {self.id}）")

        season_metadata = _make_bangumi_season_metadata(result)
        expression = config.selection.expression
        selection = parse_selection(expression) if expression is not None else None
        if selection is None:
            index, item = anchor_item
            episode = _apply_container_metadata_to_episode(_parse_bangumi_episode(item), season_metadata)
            return MediaResolveResult(media=episode, source_index=index)

        episode_items = _indexed_bangumi_episode_items(
            result,
            with_extra_episodes=config.selection.with_extra_episodes,
        )
        if config.selection.skip_preview:
            episode_items = [(index, item) for index, item in episode_items if not item.is_preview]
        episode_items = [
            (index, item)
            for index, item in episode_items
            if item.published_at is None or _publication_time_matches(item.published_at, config)
        ]
        diagnostics: list[MediaResolveDiagnostic] = []
        episode_items = _select_items(episode_items, selection, diagnostics)
        return MediaResolveResult(
            media=BangumiSeason(
                season_id=result.season_id,
                metadata=season_metadata,
                items=tuple(
                    MediaEntry(index=index, media=_parse_bangumi_episode(item)) for index, item in episode_items
                ),
            ),
            diagnostics=tuple(diagnostics),
        )


@dataclass(slots=True, kw_only=True)
class BangumiSeasonSource(MediaSource):
    id: SeasonId | MediaId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        season_id = await get_season_id_by_media(execution, self.id) if isinstance(self.id, MediaId) else self.id
        result = await get_bangumi_season(execution, season_id)
        episode_items = _indexed_bangumi_episode_items(
            result,
            with_extra_episodes=config.selection.with_extra_episodes,
        )
        if config.selection.skip_preview:
            episode_items = [(index, item) for index, item in episode_items if not item.is_preview]
        episode_items = [
            (index, item)
            for index, item in episode_items
            if item.published_at is None or _publication_time_matches(item.published_at, config)
        ]
        expression = config.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        diagnostics: list[MediaResolveDiagnostic] = []
        episode_items = _select_items(episode_items, selection, diagnostics)
        return MediaResolveResult(
            media=BangumiSeason(
                season_id=season_id,
                metadata=_make_bangumi_season_metadata(result),
                items=tuple(
                    MediaEntry(index=index, media=_parse_bangumi_episode(item)) for index, item in episode_items
                ),
            ),
            diagnostics=tuple(diagnostics),
        )


def _parse_cheese_episode(item: CheeseEpisodeInfo) -> CheeseEpisode:
    return CheeseEpisode(
        episode_id=item.episode_id,
        aid=item.aid,
        cid=item.cid,
        metadata=ItemMetaData(
            title=item.title,
            show_title=item.title,
            plot=item.title,
            thumb=item.cover,
            published_at=item.published_at or 0,
            duration=item.duration,
            added_at=get_time_stamp_by_now(),
        ),
    )


def _cheese_episode_items(
    result: CheeseSeasonInfo,
    config: ResolvedConfig,
    selection: Selection,
    diagnostics: list[MediaResolveDiagnostic],
) -> list[tuple[int, CheeseEpisodeInfo]]:
    items = [
        (index, item)
        for index, item in enumerate(result.episodes, start=1)
        if item.published_at is None or _publication_time_matches(item.published_at, config)
    ]
    return _select_items(items, selection, diagnostics)


@dataclass(slots=True, kw_only=True)
class CheeseEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        result = await get_cheese_season_by_episode(execution, self.id)
        indexed_items = list(enumerate(result.episodes, start=1))
        anchor_item = next(((index, entry) for index, entry in indexed_items if entry.episode_id == self.id), None)
        if anchor_item is None:
            raise NotFoundError(f"无法在课程 {result.title} 中找到剧集 ep{self.id}")
        expression = config.selection.expression
        if expression is None:
            index, item = anchor_item
            return MediaResolveResult(media=_parse_cheese_episode(item), source_index=index)
        selection = parse_selection(expression)
        diagnostics: list[MediaResolveDiagnostic] = []
        episode_items = _cheese_episode_items(result, config, selection, diagnostics)
        season_id = result.season_id or SeasonId(self.id.value)
        return MediaResolveResult(
            media=CheeseSeason(
                season_id=season_id,
                metadata=ItemMetaData(title=result.title),
                items=tuple(
                    MediaEntry(index=index, media=_parse_cheese_episode(item)) for index, item in episode_items
                ),
            ),
            diagnostics=tuple(diagnostics),
        )


@dataclass(slots=True, kw_only=True)
class CheeseSeasonSource(MediaSource):
    id: SeasonId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        result = await get_cheese_season(execution, self.id)
        expression = config.selection.expression
        selection = parse_selection(expression if expression is not None else "~")
        diagnostics: list[MediaResolveDiagnostic] = []
        episode_items = _cheese_episode_items(result, config, selection, diagnostics)
        return MediaResolveResult(
            media=CheeseSeason(
                season_id=self.id,
                metadata=ItemMetaData(title=result.title),
                items=tuple(
                    MediaEntry(index=index, media=_parse_cheese_episode(item)) for index, item in episode_items
                ),
            ),
            diagnostics=tuple(diagnostics),
        )


async def _resolve_bangumi_or_cheese(
    bangumi: MediaSource,
    cheese: MediaSource,
    execution: ExecutionScope,
    config: ResolvedConfig,
) -> MediaResolveResult:
    results = await asyncio.gather(
        bangumi.resolve(execution, config),
        cheese.resolve(execution, config),
        return_exceptions=True,
    )
    successes: list[MediaResolveResult] = []
    failures: list[BaseException] = []
    for result in results:
        if isinstance(result, BaseException):
            failures.append(result)
        else:
            successes.append(result)

    for failure in failures:
        if not isinstance(failure, NotFoundError):
            raise failure
    if len(successes) > 1:
        raise WrongArgumentError("该 ID 同时存在于番剧和课程命名空间，无法自动判断")
    if successes:
        return successes[0]
    raise NotFoundError("未找到对应的番剧或课程内容")


@dataclass(slots=True, kw_only=True)
class AmbiguousEpisodeSource(MediaSource):
    id: EpisodeId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        return await _resolve_bangumi_or_cheese(
            BangumiEpisodeSource(id=self.id),
            CheeseEpisodeSource(id=self.id),
            execution,
            config,
        )


@dataclass(slots=True, kw_only=True)
class AmbiguousSeasonSource(MediaSource):
    id: SeasonId

    async def resolve(self, execution: ExecutionScope, config: ResolvedConfig) -> MediaResolveResult:
        return await _resolve_bangumi_or_cheese(
            BangumiSeasonSource(id=self.id),
            CheeseSeasonSource(id=self.id),
            execution,
            config,
        )


__all__ = [
    "AmbiguousEpisodeSource",
    "AmbiguousSeasonSource",
    "BangumiEpisodeSource",
    "BangumiSeasonSource",
    "CheeseEpisodeSource",
    "CheeseSeasonSource",
    "MediaResolveDiagnostic",
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
