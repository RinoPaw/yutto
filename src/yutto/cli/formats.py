from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
    return config.with_overrides(
        {
            "resource.video": True,
            "resource.audio": True,
            "resource.danmaku": False,
            "resource.subtitle": False,
            "resource.metadata": False,
            "resource.cover": False,
            "resource.chapter_info": False,
            "resource.save_cover": False,
        }
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
    """Emit grouped preview context and formats through the download report channel."""
    if not entries:
        return

    groups = _group_format_entries(entries)
    if len(entries) == 1 and total_items == 1:
        entry = entries[0]
        emit_download_report(entry.title)
        emit_manifest_formats(entry.manifest, entry.selection)
        return

    for group_index, group in enumerate(groups, start=1):
        emit_download_report(f"格式组 {group_index}/{len(groups)}（{len(group.entries)} 个条目）")
        emit_download_report(_format_group_members(group, total_items))
        first = group.entries[0]
        emit_manifest_formats(group.manifest, first.selection)


async def resolve_format_manifests(
    execution: ExecutionScope,
    items: Sequence[MediaItem],
    config: ResolvedConfig,
) -> tuple[ResourceManifest | BaseException, ...]:
    """Resolve format manifests concurrently while respecting the configured fetch-worker limit."""
    if not items:
        return ()

    probe_limiter = asyncio.Semaphore(min(resolve_fetch_workers(config), len(items)))

    async def resolve_one(item: MediaItem) -> ResourceManifest:
        async with probe_limiter:
            return await resolve_resource_manifest(execution, item, config)

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
    relation_index: int | None,
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
            page=relation_index,
        )
    return FormatListingEntry(index=index, title=item.metadata.title, manifest=manifest, selection=selection)


@as_sync
async def run_preview_formats(
    scope_factory: ExecutionScopeFactory,
    configs: Sequence[ResolvedConfig],
    renderer: CliApplicationEventRenderer,
) -> None:
    """Preview stream formats for resolved configs without downloading media."""
    manager = DownloadManager()
    listed_streams = False

    async with renderer:
        with bind_download_event_sink(renderer), bind_download_report_sink(renderer.report):
            for config in configs:
                async with scope_factory.open(config) as execution:
                    probe_config = build_format_probe_config(config)
                    result = await manager.resolve_config(execution, probe_config)
                    if result.media is None:
                        continue

                    resolved_items = tuple(iter_media_items(result.media, source_index=result.source_index))
                    if not resolved_items:
                        continue
                    items = tuple(item for _, _, item in resolved_items)
                    if len(items) > 1:
                        concurrency = min(resolve_fetch_workers(probe_config), len(items))
                        emit_download_report(f"正在探测 {len(items)} 个条目的可用格式（并发 {concurrency}）…")

                    outcomes = await resolve_format_manifests(execution, items, probe_config)
                    entries: list[FormatListingEntry] = []
                    for index, ((ancestry, relation_index, item), outcome) in enumerate(
                        zip(resolved_items, outcomes, strict=True),
                        start=1,
                    ):
                        if isinstance(outcome, _FORMAT_RESOLUTION_ERRORS):
                            prefix = f"[{index}/{len(items)}] " if len(items) > 1 else ""
                            emit_download_report(f"{prefix}{item.metadata.title}")
                            emit_download_report(str(outcome), ReportLevel.ERROR)
                            continue
                        if isinstance(outcome, BaseException):
                            raise outcome

                        selection = select_streams(outcome, config)
                        entries.append(_make_listing_entry(index, ancestry, relation_index, item, outcome, selection))
                        listed_streams = listed_streams or bool(outcome.videos or outcome.audios)

                    emit_grouped_manifest_report(entries, total_items=len(items))

            if listed_streams:
                emit_download_report(
                    "* 表示按当前参数实际会选择的流。视频使用 -q/--video-quality 和 --vcodec；"
                    "音频使用 -aq/--audio-quality 和 --acodec。"
                )
