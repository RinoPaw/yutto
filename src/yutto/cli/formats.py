from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from yutto.config import ResolvedConfig
from yutto.core.execution import resolve_fetch_workers
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
from yutto.stream_formats import (
    FormatSignature,
    emit_manifest_formats,
    format_manifest_lines,
    manifest_format_signature,
)
from yutto.utils.functional import as_sync

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.cli.event_renderer import CliApplicationEventRenderer
    from yutto.core.execution import ExecutionScope, ExecutionScopeFactory
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


def build_format_probe_config(config: ResolvedConfig) -> ResolvedConfig:
    """Return a config that resolves only stream resources needed for format preview."""
    return replace(
        config,
        resource=replace(
            config.resource,
            video=True,
            audio=True,
            danmaku=False,
            subtitle=False,
            metadata=False,
            cover=False,
            chapter_info=False,
            save_cover=False,
        ),
    )


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


def emit_grouped_manifest_report(
    entries: Sequence[FormatListingEntry],
    *,
    total_items: int,
) -> None:
    for line in format_grouped_manifest_lines(entries, total_items=total_items):
        emit_download_report(line, ReportLevel.PLAIN)


def _group_format_entries(entries: Sequence[FormatListingEntry]) -> list[_FormatGroup]:
    groups: list[_FormatGroup] = []
    by_signature: dict[FormatSignature, _FormatGroup] = {}
    for entry in entries:
        signature = manifest_format_signature(entry.manifest)
        group = by_signature.get(signature)
        if group is None:
            group = _FormatGroup(manifest=entry.manifest, entries=[])
            by_signature[signature] = group
            groups.append(group)
        group.entries.append(entry)
    return groups


def _format_group_members(group: _FormatGroup, total_items: int) -> str:
    entries = group.entries
    if len(entries) == total_items:
        return "适用于：全部条目"

    pages_by_parent: dict[int, list[int]] = {}
    parent_titles: dict[int, str] = {}
    standalone: list[FormatListingEntry] = []
    for entry in entries:
        if entry.parent_key is None or entry.page is None:
            standalone.append(entry)
            continue
        pages_by_parent.setdefault(entry.parent_key, []).append(entry.page)
        if entry.parent_title:
            parent_titles[entry.parent_key] = entry.parent_title

    labels: list[str] = []
    for parent_key, pages in pages_by_parent.items():
        title = parent_titles.get(parent_key, f"条目 {parent_key}")
        labels.append(f"{title}（{format_index_ranges(pages, prefix='P')}）")
    labels.extend(entry.title for entry in standalone)
    return "适用于：" + "；".join(labels)


def _format_range(start: int, end: int, prefix: str) -> str:
    if start == end:
        return f"{prefix}{start}"
    return f"{prefix}{start}-{prefix}{end}"


@as_sync
async def run_preview_formats(
    scope_factory: ExecutionScopeFactory,
    configs: Sequence[ResolvedConfig],
    renderer: CliApplicationEventRenderer,
) -> None:
    """Resolve configs, fetch stream manifests, and print the grouped format matrix."""
    async with renderer:
        with bind_download_event_sink(renderer), bind_download_report_sink(renderer.report):
            for config in configs:
                async with scope_factory.open(config) as execution:
                    await _preview_one_config(execution, config)


async def _preview_one_config(execution: ExecutionScope, config: ResolvedConfig) -> None:
    probe_config = build_format_probe_config(config)
    manager = DownloadManager()
    resolved = await manager.resolve_config(execution, probe_config)
    items = list(iter_media_items(resolved.media))
    if not items:
        emit_download_report("没有可预览格式的媒体条目", ReportLevel.WARNING)
        return

    entries = await _resolve_format_entries(execution, items, probe_config)
    if entries:
        emit_grouped_manifest_report(entries, total_items=len(items))


async def _resolve_format_entries(
    execution: ExecutionScope,
    items: Sequence[tuple[MediaAncestry, MediaItem]],
    config: ResolvedConfig,
) -> list[FormatListingEntry]:
    limiter = asyncio.Semaphore(resolve_fetch_workers(config))

    async def resolve_entry(
        index: int,
        ancestry: MediaAncestry,
        item: MediaItem,
    ) -> FormatListingEntry | None:
        async with limiter:
            try:
                manifest = await resolve_resource_manifest(execution, item, config)
            except _FORMAT_RESOLUTION_ERRORS as error:
                emit_download_report(error.message, ReportLevel.ERROR)
                return None
        selection = select_streams(manifest, config)
        parent_key, parent_title, page = _format_parent_context(ancestry, item)
        return FormatListingEntry(
            index=index,
            title=_format_entry_title(item, index),
            manifest=manifest,
            selection=selection,
            parent_key=parent_key,
            parent_title=parent_title,
            page=page,
        )

    results = await asyncio.gather(
        *(resolve_entry(index, ancestry, item) for index, (ancestry, item) in enumerate(items, start=1))
    )
    return [entry for entry in results if entry is not None]


def _format_parent_context(
    ancestry: MediaAncestry,
    item: MediaItem,
) -> tuple[int | None, str | None, int | None]:
    if not isinstance(item, UgcPage) or len(ancestry) < 2:
        return None, None, None

    video = ancestry[-1].parent
    if not isinstance(video, UgcVideo) or len(video.items) <= 1:
        return None, None, None

    relation = ancestry[-2].entry
    return id(video), relation.display_title or video.metadata.title, item.page


def _format_entry_title(item: MediaItem, index: int) -> str:
    title = item.metadata.title or f"条目 {index}"
    if isinstance(item, UgcPage):
        return f"{title}（P{item.page}）"
    return title
