from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING

from yutto.core.events import DownloadStage, DownloadStageChanged
from yutto.core.operation import emit_download_event, emit_download_report
from yutto.downloader.executor import DownloadExecutor
from yutto.downloader.planner import DownloadPlanner

if TYPE_CHECKING:
    from pathlib import Path

    from yutto.core.execution import ExecutionScope
    from yutto.core.options import DownloadOptions
    from yutto.core.result import ItemResult
    from yutto.downloader.path_leases import DownloadPathLeasePool
    from yutto.resource import ResourceManifest
    from yutto.utils.metadata import ItemMetaData


async def process_download(
    scope: ExecutionScope,
    manifest: ResourceManifest,
    metadata: ItemMetaData,
    path: Path,
    options: DownloadOptions,
    *,
    path_leases: DownloadPathLeasePool | None = None,
) -> ItemResult:
    """Plan and execute one MediaItem from its resolved resource manifest."""
    item = path.name
    emit_download_report(f"开始处理视频 {item}")
    emit_download_event(DownloadStageChanged(name=DownloadStage.PREPARING, item=item))
    plan = DownloadPlanner().plan(manifest, path, options)
    lease = (
        path_leases.lease(
            (
                plan.paths.output.with_suffix(""),
                plan.paths.temporary_dir / plan.paths.output.stem,
            )
        )
        if path_leases is not None
        else nullcontext()
    )
    async with lease:
        return await DownloadExecutor().execute(scope, manifest, metadata, plan)
