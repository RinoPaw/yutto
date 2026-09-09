from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, cast

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
    PathOptions,
    filter_media_by_publication_time,
    iter_media_items,
    resolve_media_paths,
)
from yutto.media import MediaContainer, UgcFav, UgcVideo
from yutto.parser import parse
from yutto.path_templates import create_unique_path_resolver
from yutto.resource import resolve_resource_manifest
from yutto.source import MediaResolveFailure, MediaResolveResult
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.filter import PublicationTimeFilter

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.core.execution import ExecutionScope, ExecutionScopeFactory
    from yutto.core.request import DownloadRequest
    from yutto.media import Media, MediaItem


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


def _has_media_items(media: Media | None) -> bool:
    return media is not None and next(iter_media_items(media), None) is not None


def _report_resolve_failures(failures: tuple[MediaResolveFailure, ...]) -> None:
    for failure in failures:
        emit_download_report(
            f"第 {failure.index} 项 {failure.source}：{failure.error.message}",
            ReportLevel.ERROR,
        )


def _raise_all_resolve_failures(failures: tuple[MediaResolveFailure, ...]) -> None:
    if len(failures) == 1:
        raise failures[0].error
    raise ResolveFailedError(f"解析未得到任何条目：{len(failures)} 个子项解析失败（详见日志）")


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
        failures: list[MediaResolveFailure] = []
        for request in requests:
            async with scope_factory.open(request) as scope:
                result = await self.resolve_request(scope, request)
                failures.extend(result.failures)
                if result.media is not None:
                    media.append(result.media)

        resolved_failures = tuple(
            ResolveFailure(
                type=type(failure.error).__name__,
                message=failure.error.message,
                code=failure.error.code.value,
            )
            for failure in failures
        )
        return ResolveResult(items=tuple(media), failures=resolved_failures)

    async def process_request(
        self,
        scope: ExecutionScope,
        request: DownloadRequest,
    ) -> tuple[ItemResult, ...]:
        result = await self.resolve_request(scope, request)
        if result.media is None:
            return ()

        path_entries = resolve_media_paths(
            result.media,
            PathOptions(subpath_template=request.output.subpath_template),
        )
        download_list = tuple((entry.ancestry, entry.item) for entry in path_entries)
        prepared: list[tuple[MediaAncestry, MediaItem, Path, str | None]] = []
        current_display_group: str | None = None
        for entry in path_entries:
            path = Path(self.unique_path(str(entry.path)))
            prepared.append((entry.ancestry, entry.item, path, current_display_group))
            current_display_group = _display_group(entry.ancestry)

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

                parent = ancestry[-1] if ancestry else None
                try:
                    manifest = await resolve_resource_manifest(
                        scope,
                        cast(MediaContainer, parent),
                        item,
                        resource_options,
                    )
                except (NoAccessPermissionError, HttpStatusError, UnSupportedTypeError, NotFoundError) as error:
                    emit_download_report(error.message, ReportLevel.ERROR)
                    if index + 1 < len(start_turns):
                        start_turns[index + 1].set()
                    return

                if request.output.enforce_directory_boundary:
                    ensure_output_path_is_scoped(
                        path,
                        request.output.directory,
                        request.output.temporary_directory or request.output.directory,
                    )
                if len(download_list) > 1:
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
                    manifest,
                    item.metadata,
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
    ) -> MediaResolveResult:
        """Resolve Parser -> MediaSource -> Media and apply generic Media filters."""
        value = request.source.url.strip()
        source = parse(value)
        if source is None:
            try:
                redirected_value = unwrap_fetch_result(await Fetcher.get_redirected_url(scope, value))
            except InvalidUrlError:
                raise WrongUrlError(f"无效的 url({value})～请检查一下链接是否正确～") from None
            except UnsupportedProtocolError:
                raise WrongUrlError(f"无效的 url 协议（{value}）～请检查一下链接协议是否正确") from None

            source = parse(redirected_value)
            if source is None:
                raise WrongUrlError(f"无法识别 url（{redirected_value}）")

        source_options = source_options_from_request(request)
        emit_download_event(DownloadStageChanged(name=DownloadStage.RESOLVING))

        if not await validate_user_info(
            scope,
            {"is_login": request.access.login_strict, "vip_status": request.access.vip_strict},
        ):
            raise NotLoginError("启用了严格校验大会员或登录模式，请检查认证信息（--auth）或大会员状态！")

        result = await source.resolve(scope, source_options)
        if result.media is None:
            raise TypeError(f"{type(source).__name__}.resolve() returned no media")

        _report_resolve_failures(result.failures)
        if result.failures and not _has_media_items(result.media):
            _raise_all_resolve_failures(result.failures)

        if request.selection.start_time is not None or request.selection.end_time is not None:
            publication_time_filter = PublicationTimeFilter.from_strings(
                request.selection.start_time,
                request.selection.end_time,
            )
            return MediaResolveResult(
                media=filter_media_by_publication_time(result.media, publication_time_filter),
                failures=result.failures,
            )
        return result


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
