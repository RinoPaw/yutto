from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto.core.operation import (
    ReportLevel,
    bind_download_event_sink,
    bind_download_report_sink,
    emit_download_report,
)
from yutto.download_manager import DownloadManager
from yutto.downloader.selector import select_streams
from yutto.exceptions import HttpStatusError, NoAccessPermissionError, NotFoundError, UnSupportedTypeError
from yutto.listing import iter_media_items
from yutto.media import UgcPage, UgcVideo
from yutto.resource import ResourceManifest, resolve_resource_manifest
from yutto.stream_formats import FormatSignature, format_manifest_lines, manifest_format_signature
from yutto.utils.console.logger import Logger
from yutto.utils.functional import as_sync

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.cli.event_renderer import CliApplicationEventRenderer
    from yutto.core.execution import ExecutionScope, ExecutionScopeFactory
    from yutto.core.request import DownloadRequest
    from yutto.downloader.selector import StreamSelection
    from yutto.listing import MediaAncestry
    from yutto.media import MediaItem


_FORMAT_RESOLUTION_ERRORS = (NoAccessPermissionError, HttpStatusError, UnSupportedTypeError, NotFoundError)


@dataclass(frozen=True, slots=True)
class FormatListingEntry:
    index: int
    title: str
    manifest: ResourceManifest
    selection: StreamSelection | None = None
    parent_key: int | None = None
    parent_title: str | None = None
    page: int | None = None


@dataclass(slots=True)
class _FormatGroup:
    manifest: ResourceManifest
    entries: list[FormatListingEntry]


def build_format_probe_request(request: DownloadRequest) -> DownloadRequest:
    """Return a request that resolves only the stream resources needed for format listing."""
    resources = request.resources.model_copy(
        update={
            "video": True,
            "audio": True,
            "danmaku": False,
            "subtitle": False,
            "metadata": False,
            "cover": False,
            "chapter_info": False,
            "save_cover": False,
        }
    )
    return request.model_copy(update={"resources": resources})


def format_index_ranges(indexes: Sequence[int], *, prefix: str = "") -> str:
    """Compress integer indexes into human-readable ranges such as P1-P3, P5."""
    ordered = sorted(set(indexes))
    if not ordered:
        return "-"

    ranges: list[str] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(_format_range(start, previous, prefix))
        start = previous = value
    ranges.append(_format_range(start, previous, prefix))
    return ", ".join(ranges)


def format_grouped_manifest_lines(
    entries: Sequence[FormatListingEntry],
    *,
    total_items: int,
) -> tuple[str, ...]:
    """Render equal format sets once and summarize which resolved items share each set."""
    if not entries:
        return ()

    groups = _group_format_entries(entries)
    if len(entries) == 1 and total_items == 1:
        entry = entries[0]
        return (entry.title, *format_manifest_lines(entry.manifest, entry.selection))

    lines: list[str] = []
    for group_index, group in enumerate(groups, start=1):
        lines.append(f"格式组 {group_index}/{len(groups)}（{len(group.entries)} 个条目）")
        lines.append(_format_group_members(group, total_items))
        first = group.entries[0]
        lines.extend(format_manifest_lines(group.manifest, first.selection))
        if group_index != len(groups):
            lines.append("")
    return tuple(lines)


async def resolve_format_manifests(
    scope: ExecutionScope,
    items: Sequence[MediaItem],
    request: DownloadRequest,
) -> tuple[ResourceManifest | BaseException, ...]:
    """Resolve format manifests concurrently while respecting the configured fetch-worker limit."""
    if not items:
        return ()

    probe_limiter = asyncio.Semaphore(min(request.network.fetch_workers, len(items)))

    async def resolve_one(item: MediaItem) -> ResourceManifest:
        async with probe_limiter:
            return await resolve_resource_manifest(scope, item, request)

    results = await asyncio.gather(*(resolve_one(item) for item in items), return_exceptions=True)
    return tuple(results)


def _format_range(start: int, end: int, prefix: str) -> str:
    if start == end:
        return f"{prefix}{start}"
    return f"{prefix}{start}-{prefix}{end}"


def _group_format_entries(entries: Sequence[FormatListingEntry]) -> tuple[_FormatGroup, ...]:
    groups: dict[FormatSignature, _FormatGroup] = {}
    for entry in entries:
        signature = manifest_format_signature(entry.manifest)
        group = groups.get(signature)
        if group is None:
            group = _FormatGroup(manifest=entry.manifest, entries=[])
            groups[signature] = group
        group.entries.append(entry)
    return tuple(groups.values())


def _format_group_members(group: _FormatGroup, total_items: int) -> str:
    entries = group.entries
    first = entries[0]
    if (
        first.parent_key is not None
        and first.page is not None
        and all(entry.parent_key == first.parent_key and entry.page is not None for entry in entries)
    ):
        pages = [entry.page for entry in entries if entry.page is not None]
        parent_title = first.parent_title or first.title
        return f"{parent_title}: {format_index_ranges(pages, prefix='P')}"

    indexes = [entry.index for entry in entries]
    range_text = format_index_ranges(indexes)
    if len(entries) == 1:
        return f"[{first.index}/{total_items}] {first.title}"
    return f"条目 {range_text}/{total_items}: {first.title} … {entries[-1].title}"


def _make_listing_entry(
    index: int,
    ancestry: MediaAncestry,
    item: MediaItem,
    manifest: ResourceManifest,
    selection: StreamSelection,
) -> FormatListingEntry:
    parent = ancestry[-1] if ancestry else None
    if isinstance(item, UgcPage) and isinstance(parent, UgcVideo):
        return FormatListingEntry(
            index=index,
            title=item.metadata.title,
            manifest=manifest,
            selection=selection,
            parent_key=id(parent),
            parent_title=parent.metadata.title,
            page=item.page,
        )
    return FormatListingEntry(index=index, title=item.metadata.title, manifest=manifest, selection=selection)


@as_sync
async def run_list_formats(
    scope_factory: ExecutionScopeFactory,
    requests: Sequence[DownloadRequest],
    renderer: CliApplicationEventRenderer,
) -> None:
    """Resolve and display stream formats for CLI requests without downloading media."""
    manager = DownloadManager()
    listed_streams = False

    async with renderer:
        with bind_download_event_sink(renderer), bind_download_report_sink(renderer.report):
            for request in requests:
                async with scope_factory.open(request) as scope:
                    probe_request = build_format_probe_request(request)
                    result = await manager.resolve_request(scope, probe_request)
                    if result.media is None:
                        continue

                    resolved_items = tuple(iter_media_items(result.media))
                    if not resolved_items:
                        continue
                    items = tuple(item for _, item in resolved_items)
                    if len(items) > 1:
                        concurrency = min(probe_request.network.fetch_workers, len(items))
                        Logger.print(f"正在探测 {len(items)} 个条目的可用格式（并发 {concurrency}）…")

                    outcomes = await resolve_format_manifests(scope, items, probe_request)
                    entries: list[FormatListingEntry] = []
                    for index, ((ancestry, item), outcome) in enumerate(
                        zip(resolved_items, outcomes, strict=True),
                        start=1,
                    ):
                        if isinstance(outcome, _FORMAT_RESOLUTION_ERRORS):
                            prefix = f"[{index}/{len(items)}] " if len(items) > 1 else ""
                            Logger.print(f"{prefix}{item.metadata.title}")
                            emit_download_report(str(outcome), ReportLevel.ERROR)
                            Logger.print("")
                            continue
                        if isinstance(outcome, BaseException):
                            raise outcome

                        selection = select_streams(outcome, request)
                        entries.append(_make_listing_entry(index, ancestry, item, outcome, selection))
                        listed_streams = listed_streams or bool(outcome.videos or outcome.audios)

                    for line in format_grouped_manifest_lines(entries, total_items=len(items)):
                        Logger.print(line)
                    if entries:
                        Logger.print("")

    if listed_streams:
        Logger.print("* 表示按当前参数实际会选择的流。视频使用 -q/--video-quality 和 --vcodec；音频使用 -aq/--audio-quality 和 --acodec。")
