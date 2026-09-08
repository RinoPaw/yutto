from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from yutto._native import TransferWorkerLimit, wait_for_transfer
from yutto.downloader.progressbar import show_progress
from yutto.exceptions import MaxRetryError
from yutto.utils.asynclib import NoSuccessfulResultError, make_coroutine_factory, race_for_first_success
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from typing import Any

    from yutto.core.execution import ExecutionScope


def create_mirrors_filter(banned_mirrors_pattern: str | None) -> Callable[[list[str]], list[str]]:
    mirror_filter: Callable[[str], bool]
    if banned_mirrors_pattern is None:
        mirror_filter = lambda _: True  # noqa: E731
    else:
        regex_banned_pattern = re.compile(banned_mirrors_pattern)
        mirror_filter = lambda url: not regex_banned_pattern.search(url)  # noqa: E731

    def mirrors_filter(mirrors: list[str]) -> list[str]:
        return list(filter(mirror_filter, mirrors))

    return mirrors_filter


async def _probe_media_size(scope: ExecutionScope, url: str, mirrors: Iterable[str]) -> int:
    async def probe(candidate: str) -> int:
        size = unwrap_fetch_result(await Fetcher.get_size(scope, candidate))
        if size is None:
            raise MaxRetryError("媒体大小探测未返回长度")
        return size

    create_probe = make_coroutine_factory(probe)
    try:
        return await race_for_first_success(create_probe(candidate) for candidate in (url, *mirrors))
    except NoSuccessfulResultError as error:
        if len(error.exceptions) == 1 and isinstance(error.exceptions[0], MaxRetryError):
            raise error.exceptions[0] from None
        if not error.exceptions:
            raise MaxRetryError("媒体大小探测失败：所有地址均已取消") from error
        raise MaxRetryError(f"媒体大小探测失败：{len(error.exceptions)} 个地址均不可用") from ExceptionGroup(
            "all media size probes failed", error.exceptions
        )


async def download_files(
    scope: ExecutionScope,
    sources: Sequence[tuple[str, Sequence[str]]],
    *,
    block_size: int,
    banned_mirrors_pattern: str | None,
) -> tuple[Path, ...]:
    """Download URL candidates into transfer-owned temporary files and return those files."""

    if not sources:
        return ()

    staging_directory = Path(tempfile.mkdtemp(prefix="yutto-download-"))
    mirrors_filter = create_mirrors_filter(banned_mirrors_pattern)
    prepared_transfers: list[tuple[list[str], Path, int]] = []

    try:
        for index, (url, mirrors) in enumerate(sources):
            filtered_mirrors = mirrors_filter(list(mirrors))
            size = await _probe_media_size(scope, url, filtered_mirrors)
            suffix = Path(urlsplit(url).path).suffix or ".bin"
            target = staging_directory / f"{index:02}{suffix}.part"
            prepared_transfers.append(([url, *filtered_mirrors], target, size))

        handles = []
        wait_tasks: list[asyncio.Task[int]] = []
        progress_task: asyncio.Task[None] | None = None
        worker_limit = TransferWorkerLimit(scope.download_workers)
        batch_size = 1 if scope.download_workers == 1 else len(prepared_transfers)

        try:
            for batch_start in range(0, len(prepared_transfers), batch_size):
                batch_tasks = []
                batch_handles = []
                for source_urls, target, size in prepared_transfers[batch_start : batch_start + batch_size]:
                    handle = scope.session.start_transfer(
                        source_urls,
                        target,
                        size,
                        overwrite=False,
                        workers=scope.download_workers,
                        block_size=block_size,
                        worker_limit=worker_limit,
                    )
                    handles.append(handle)
                    batch_handles.append(handle)
                    wait_task = asyncio.create_task(wait_for_transfer(handle))
                    wait_tasks.append(wait_task)
                    batch_tasks.append(wait_task)

                total_size = sum(
                    size for _, _, size in prepared_transfers[batch_start : batch_start + batch_size]
                )
                progress_task = asyncio.create_task(show_progress(batch_handles, total_size))
                await _wait_for_native_transfers(batch_tasks)
                await progress_task
                progress_task = None
        finally:
            if progress_task is not None:
                if not progress_task.done():
                    progress_task.cancel()
                await asyncio.gather(progress_task, return_exceptions=True)
            cleanup_task = asyncio.create_task(_cancel_and_reap_native_transfers(handles, wait_tasks))
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                await cleanup_task
                raise
    except BaseException:
        shutil.rmtree(staging_directory, ignore_errors=True)
        raise

    return tuple(target for _, target, _ in prepared_transfers)


async def _wait_for_native_transfers(wait_tasks: Iterable[asyncio.Task[int]]) -> None:
    try:
        await asyncio.gather(*wait_tasks)
    except RuntimeError as error:
        raise MaxRetryError(f"媒体下载失败：{error}") from error


async def _cancel_and_reap_native_transfers(handles: Iterable[Any], wait_tasks: Iterable[asyncio.Task[int]]) -> None:
    for handle in handles:
        if not handle.done():
            handle.cancel()
    await asyncio.gather(*wait_tasks, return_exceptions=True)
