from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from yutto._native import InvalidUrlError, UnsupportedProtocolError
from yutto.auth import validate_user_info
from yutto.core.events import DownloadStage, DownloadStageChanged
from yutto.core.operation import ReportLevel, emit_download_event, emit_download_report
from yutto.core.options import resource_options_from_request, source_options_from_request
from yutto.core.result import DownloadResult, ItemResult, ResolveFailure, ResolveResult
from yutto.downloader.downloader import process_download
from yutto.downloader.path_leases import DownloadPathLeasePool
from yutto.exceptions import (
    HttpStatusError,
    NoAccessPermissionError,
    NotFoundError,
    NotLoginError,
    ResolveFailedError,
    UnSupportedTypeError,
    WrongArgumentError,
    WrongUrlError,
)
from yutto.listing import (
    MediaAncestry,
    filter_media_tree,
    iter_media_items,
    media_item_pubdate,
    resolve_media_path,
)
from yutto.media import UgcFav, UgcVideo
from yutto.parser import parse
from yutto.path_templates import create_unique_path_resolver
from yutto.resource import resolve_media_item
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.filter import PublicationTimeFilter
from yutto.utils.metadata import attach_chapter_info

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from yutto.core.execution import ExecutionScope, ExecutionScopeFactory
    from yutto.core.request import DownloadRequest
    from yutto.exceptions import YuttoBaseException
    from yutto.media import Media, MediaItem
    from yutto.source import MediaSource


def show_batch_episode_title(
    display_group: str | None,
    path: Path,
    index: int,
    total: int,
    current_display_group: str | None,
) -> str | None:
    if display_group is not None and display_group != current_display_group:
        emit_download_report(display_group, badge="列表")
        current_display_group = display_group
    elif display_group is None:
        current_display_group = None

    display_name = path.name
    if display_group is not None:
        display_name = f"  {display_name}"
    emit_download_report(display_name, badge=f"[{index}/{total}]")
    return current_display_group


def _display_group(ancestry: MediaAncestry) -> str | None:
    if len(ancestry) < 2:
        return None
    root = ancestry[-2]
    video = ancestry[-1]
    if isinstance(root, UgcFav) and isinstance(video, UgcVideo) and len(video.items) > 1:
        return video.metadata.title
    return None


async def _resolve_source(scope: ExecutionScope, value: str) -> MediaSource:
    value = value.strip()
    if source := parse(value):
        return source

    try:
        redirected_value = unwrap_fetch_result(await Fetcher.get_redirected_url(scope, value))
    except InvalidUrlError:
        raise WrongUrlError(f"无效的 url({value})～请检查一下链接是否正确～") from None
    except UnsupportedProtocolError:
        raise WrongUrlError(f"无效的 url 协议（{value}）～请检查一下链接协议是否正确") from None

    if source := parse(redirected_value):
        return source
    raise WrongUrlError(f"无法识别 url（{redirected_value}）")


def _iter_request_items(
    media: Media,
    request: DownloadRequest,
) -> Iterator[tuple[MediaAncestry, MediaItem]]:
    publication_time_filter = PublicationTimeFilter.from_strings(
        request.selection.start_time,
        request.selection.end_time,
    )
    filter_by_time = request.selection.start_time is not None or request.selection.end_time is not None
    for ancestry, item in iter_media_items(media):
        if filter_by_time and not publication_time_filter.matches(media_item_pubdate(ancestry, item)):
            continue
        yield ancestry, item


@dataclass(frozen=True, slots=True)
class _ResolvedRequestOutcome:
    source: MediaSource | None = None
    media: Media | None = None
    failures: tuple[YuttoBaseException, ...] = ()


class DownloadManager:
    """Execute requests with bounded item concurrency and one explicit scope per request."""

    def __init__(self, *, jobs: int = 1, path_leases: DownloadPathLeasePool | None = None):
        if jobs < 1:
            raise ValueError("jobs must be at least 1")
        self.jobs = jobs
        self.unique_path = create_unique_path_resolver()
        self.path_leases = path_leases or DownloadPathLeasePool()
        self._item_limiter = asyncio.Semaphore(jobs)

    async def execute(
        self,
        scope_factory: ExecutionScopeFactory,
        requests: Sequence[DownloadRequest],
    ) -> DownloadResult:
        results: list[tuple[ItemResult, ...] | None] = [None] * len(requests)
        next_index = 0
        failed = False

        async def run_requests() -> None:
            nonlocal failed, next_index
            while not failed and next_index < len(requests):
                index = next_index
                next_index += 1
                request = requests[index]
                try:
                    async with scope_factory.open(request) as scope:
                        results[index] = await self.process_request(scope, request)
                except BaseException:
                    failed = True
                    raise

        tasks = [
            asyncio.create_task(run_requests(), name=f"yutto-request-worker-{index}")
            for index in range(min(self.jobs, len(requests)))
        ]
        await _gather_cancelling(tasks)
        return DownloadResult(items=tuple(item for result in results if result is not None for item in result))

    async def execute_resolve(
        self,
        scope_factory: ExecutionScopeFactory,
        requests: Sequence[DownloadRequest],
    ) -> ResolveResult:
        media: list[Media] = []
        failures: list[YuttoBaseException] = []
        for request in requests:
            async with scope_factory.open(request) as scope:
                outcome = await self.resolve_request(scope, request)
                failures.extend(outcome.failures)
                if outcome.media is None:
                    continue

                publication_time_filter = PublicationTimeFilter.from_strings(
                    request.selection.start_time,
                    request.selection.end_time,
                )
                filter_by_time = request.selection.start_time is not None or request.selection.end_time is not None
                selected_media = filter_media_tree(
                    outcome.media,
                    lambda ancestry, item: not filter_by_time
                    or publication_time_filter.matches(media_item_pubdate(ancestry, item)),
                )
                if selected_media is not None:
                    media.append(selected_media)

        if failures and not media:
            if len(failures) == 1:
                raise failures[0]
            raise ResolveFailedError(f"解析未得到任何条目：{len(failures)} 个来源/条目解析失败（详见 server 日志）")
        resolved_failures = tuple(
            ResolveFailure(type=type(error).__name__, message=error.message, code=error.code.value)
            for error in failures
        )
        return ResolveResult(media=tuple(media), failures=resolved_failures)

    async def process_request(
        self,
        scope: ExecutionScope,
        request: DownloadRequest,
    ) -> tuple[ItemResult, ...]:
        outcome = await self.resolve_request(scope, request)
        if outcome.source is None or outcome.media is None:
            if len(outcome.failures) == 1:
                raise outcome.failures[0]
            if outcome.failures:
                raise ResolveFailedError(
                    f"解析未得到任何条目：{len(outcome.failures)} 个来源/条目解析失败（详见 server 日志）"
                )
            return ()

        download_list = tuple(_iter_request_items(outcome.media, request))
        prepared: list[tuple[MediaAncestry, MediaItem, Path, str | None]] = []
        current_display_group: str | None = None
        for ancestry, item in download_list:
            path = Path(self.unique_path(str(resolve_media_path(outcome.source, ancestry, item, request))))
            prepared.append((ancestry, item, path, current_display_group))
            current_display_group = _display_group(ancestry)

        if request.network.download_interval > 0 and len(prepared) > 1:
            emit_download_report(f"下载任务启动间隔 {request.network.download_interval} 秒")

        results: list[ItemResult | None] = [None] * len(prepared)
        start_turns = [asyncio.Event() for _ in prepared]
        if start_turns:
            start_turns[0].set()
        resource_options = resource_options_from_request(request)

        async def run_item(
            index: int,
            ancestry: MediaAncestry,
            item: MediaItem,
            path: Path,
            previous_display_group: str | None,
        ) -> None:
            if index > 0 and request.network.download_interval > 0:
                await asyncio.sleep(index * request.network.download_interval)
            await start_turns[index].wait()
            async with self._item_limiter:
                if not await validate_user_info(
                    scope,
                    {"is_login": request.access.login_strict, "vip_status": request.access.vip_strict},
                ):
                    raise NotLoginError("启用了严格校验大会员或登录模式，请检查认证信息（--auth）或大会员状态！")

                if not ancestry:
                    raise TypeError(f"downloadable media item has no parent: {type(item).__name__}")
                try:
                    resources = await resolve_media_item(
                        scope,
                        ancestry[-1],
                        item,
                        resource_options,
                    )
                except (NoAccessPermissionError, HttpStatusError, UnSupportedTypeError, NotFoundError) as error:
                    emit_download_report(error.message, ReportLevel.ERROR)
                    if index + 1 < len(start_turns):
                        start_turns[index + 1].set()
                    return

                metadata = resources.metadata
                if metadata is not None and resources.chapter_info_data:
                    attach_chapter_info(metadata, list(resources.chapter_info_data))

                if request.output.enforce_directory_boundary:
                    ensure_output_path_is_scoped(
                        path,
                        request.output.directory,
                        request.output.temporary_directory or request.output.directory,
                    )
                if request.scope.batch:
                    show_batch_episode_title(
                        _display_group(ancestry),
                        path,
                        index + 1,
                        len(download_list),
                        previous_display_group,
                    )
                if index + 1 < len(start_turns):
                    start_turns[index + 1].set()
                results[index] = await process_download(
                    scope,
                    resources,
                    path,
                    request,
                    path_leases=self.path_leases,
                )

        tasks = [
            asyncio.create_task(
                run_item(index, ancestry, item, path, previous_display_group),
                name=f"yutto-item-{index}",
            )
            for index, (ancestry, item, path, previous_display_group) in enumerate(prepared)
        ]
        await _gather_cancelling(tasks)
        emit_download_report("", ReportLevel.PLAIN)
        return tuple(result for result in results if result is not None)

    async def resolve_request(
        self,
        scope: ExecutionScope,
        request: DownloadRequest,
    ) -> _ResolvedRequestOutcome:
        """Resolve Parser -> MediaSource -> Media without flattening the media tree."""
        source = await _resolve_source(scope, request.source.url)
        source_options = source_options_from_request(request)
        emit_download_event(DownloadStageChanged(name=DownloadStage.RESOLVING))

        if not await validate_user_info(
            scope,
            {"is_login": request.access.login_strict, "vip_status": request.access.vip_strict},
        ):
            raise NotLoginError("启用了严格校验大会员或登录模式，请检查认证信息（--auth）或大会员状态！")

        try:
            media = await source.resolve(scope, source_options)
        except (NoAccessPermissionError, HttpStatusError, UnSupportedTypeError, NotFoundError, NotLoginError) as error:
            emit_download_report(error.message, ReportLevel.ERROR)
            return _ResolvedRequestOutcome(source=source, failures=(error,))

        return _ResolvedRequestOutcome(source=source, media=media)


def ensure_output_path_is_scoped(path: Path, output_root: Path, temporary_root: Path) -> None:
    if path.is_absolute() or path.anchor or ".." in path.parts:
        raise WrongArgumentError("解析后的输出路径超出了 server 配置的根目录")
    for root in (output_root.resolve(), temporary_root.resolve()):
        if not (root / path).resolve().is_relative_to(root):
            raise WrongArgumentError("解析后的输出路径超出了 server 配置的根目录")


async def _gather_cancelling(tasks: Sequence[asyncio.Task[None]]) -> None:
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
