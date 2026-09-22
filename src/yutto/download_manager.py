from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.auth import validate_user_info
from yutto.core.events import DownloadStage, DownloadStageChanged
from yutto.core.operation import ReportLevel, emit_download_event, emit_download_report
from yutto.core.result import DownloadResult, ItemResult, ResolveFailure, ResolveResult
from yutto.downloader.downloader import process_download
from yutto.downloader.path_leases import DownloadPathLeasePool
from yutto.downloader.planner import resolve_output_directories
from yutto.exceptions import (
    HttpStatusError,
    NoAccessPermissionError,
    NotFoundError,
    NotLoginError,
    ResolveFailedError,
    UnSupportedTypeError,
    WrongArgumentError,
)
from yutto.listing import MediaAncestry, iter_media_items, resolve_media_paths
from yutto.media import UgcFav, UgcVideo
from yutto.parser import parse
from yutto.path_templates import create_unique_path_resolver
from yutto.resource import resolve_resource_manifest
from yutto.scope import MISSING, Scope
from yutto.url_resolver import resolve_redirected_source

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.core.execution import ExecutionScope, ExecutionScopeFactory
    from yutto.media import Media, MediaItem
    from yutto.source import MediaResolveFailure, MediaResolveResult


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


def _scope_bool(value: object, default: bool = False) -> bool:
    return default if value is MISSING else bool(value)


def _scope_int(value: object, default: int = 0) -> int:
    if value is MISSING:
        return default
    if isinstance(value, bool):
        raise ValueError("expected an integer Scope value")
    return int(value)


class DownloadManager:
    """Execute parameter scopes with bounded item concurrency and one runtime context per scope."""

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
        scopes: Sequence[Scope],
    ) -> DownloadResult:
        results: list[tuple[ItemResult, ...] | None] = [None] * len(scopes)
        next_index = 0
        failed = False

        async def run_scopes() -> None:
            nonlocal failed, next_index
            while not failed and next_index < len(scopes):
                index = next_index
                next_index += 1
                parameter_scope = scopes[index]
                try:
                    async with scope_factory.open(parameter_scope) as execution:
                        results[index] = await self.process_scope(execution, parameter_scope)
                except BaseException:
                    failed = True
                    raise

        tasks = [
            asyncio.create_task(run_scopes(), name=f"yutto-scope-worker-{index}")
            for index in range(min(self.jobs, len(scopes)))
        ]
        await _gather_cancelling(tasks)
        return DownloadResult(items=tuple(item for result in results if result is not None for item in result))

    async def execute_resolve(
        self,
        scope_factory: ExecutionScopeFactory,
        scopes: Sequence[Scope],
    ) -> ResolveResult:
        media: list[Media] = []
        failures: list[MediaResolveFailure] = []
        for parameter_scope in scopes:
            async with scope_factory.open(parameter_scope) as execution:
                result = await self.resolve_scope(execution, parameter_scope)
                failures.extend(result.failures)
                if result.media is not None:
                    media.append(result.media)

        if failures and not any(_has_media_items(item) for item in media):
            _raise_all_resolve_failures(tuple(failures))

        resolved_failures = tuple(
            ResolveFailure(
                type=type(failure.error).__name__,
                message=failure.error.message,
                code=failure.error.code.value,
            )
            for failure in failures
        )
        return ResolveResult(items=tuple(media), failures=resolved_failures)

    async def process_scope(
        self,
        execution: ExecutionScope,
        scope: Scope,
    ) -> tuple[ItemResult, ...]:
        result = await self.resolve_scope(execution, scope)
        if result.media is None:
            return ()

        template = scope.output.subpath_template
        subpath_template = "{auto}" if template is MISSING else str(template)
        path_entries = resolve_media_paths(result.media, subpath_template=subpath_template)
        download_list = tuple((entry.ancestry, entry.item) for entry in path_entries)
        prepared: list[tuple[MediaAncestry, MediaItem, Path, str | None]] = []
        current_display_group: str | None = None
        for entry in path_entries:
            path = Path(self.unique_path(str(entry.path)))
            prepared.append((entry.ancestry, entry.item, path, current_display_group))
            current_display_group = _display_group(entry.ancestry)

        download_interval = _scope_int(scope.network.download_interval)
        if download_interval > 0 and len(prepared) > 1:
            emit_download_report(f"下载任务启动间隔 {download_interval} 秒")

        login_strict = _scope_bool(scope.auth.login_strict)
        vip_strict = _scope_bool(scope.auth.vip_strict)
        output_directory, temporary_directory = resolve_output_directories(scope)

        results: list[ItemResult | None] = [None] * len(prepared)
        start_turns = [asyncio.Event() for _ in prepared]
        if start_turns:
            start_turns[0].set()

        async def run_item(
            index: int,
            ancestry: MediaAncestry,
            item: MediaItem,
            path: Path,
            previous_display_group: str | None,
        ) -> None:
            if index > 0 and download_interval > 0:
                await asyncio.sleep(index * download_interval)
            await start_turns[index].wait()
            async with self._item_limiter:
                if not await validate_user_info(
                    execution,
                    {"is_login": login_strict, "vip_status": vip_strict},
                ):
                    raise NotLoginError("启用了严格校验大会员或登录模式，请检查认证信息（--auth）或大会员状态！")

                try:
                    manifest = await resolve_resource_manifest(execution, item, scope)
                except (NoAccessPermissionError, HttpStatusError, UnSupportedTypeError, NotFoundError) as error:
                    emit_download_report(error.message, ReportLevel.ERROR)
                    if index + 1 < len(start_turns):
                        start_turns[index + 1].set()
                    return
                if execution.enforce_output_boundary:
                    ensure_output_path_is_scoped(path, output_directory, temporary_directory)
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
                    execution,
                    manifest,
                    item.metadata,
                    path,
                    scope,
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

    async def resolve_scope(
        self,
        execution: ExecutionScope,
        scope: Scope,
    ) -> MediaResolveResult:
        """Resolve Parser -> MediaSource -> Media for one parameter Scope."""
        value = scope.source.value
        if value is MISSING or value is None:
            raise ValueError("download source is missing")
        source_text = str(value).strip()
        source = parse(source_text)
        if source is None:
            source = await resolve_redirected_source(execution, source_text)

        emit_download_event(DownloadStageChanged(name=DownloadStage.RESOLVING))

        if not await validate_user_info(
            execution,
            {
                "is_login": _scope_bool(scope.auth.login_strict),
                "vip_status": _scope_bool(scope.auth.vip_strict),
            },
        ):
            raise NotLoginError("启用了严格校验大会员或登录模式，请检查认证信息（--auth）或大会员状态！")

        result = await source.resolve(execution, scope)
        if result.media is None and not result.failures:
            raise TypeError(f"{type(source).__name__}.resolve() returned no media")

        _report_resolve_failures(result.failures)
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
