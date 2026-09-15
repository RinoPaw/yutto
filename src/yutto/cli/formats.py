from __future__ import annotations

from typing import TYPE_CHECKING

from yutto.core.operation import (
    ReportLevel,
    bind_download_event_sink,
    bind_download_report_sink,
    emit_download_report,
)
from yutto.download_manager import DownloadManager
from yutto.exceptions import HttpStatusError, NoAccessPermissionError, NotFoundError, UnSupportedTypeError
from yutto.listing import iter_media_items
from yutto.media.quality import audio_quality_map, video_quality_map
from yutto.resource import ResourceManifest, resolve_resource_manifest
from yutto.utils.console.formatter import get_string_width
from yutto.utils.console.logger import Logger
from yutto.utils.functional import as_sync

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.cli.event_renderer import CliApplicationEventRenderer
    from yutto.core.execution import ExecutionScopeFactory
    from yutto.core.request import DownloadRequest


_FORMAT_RESOLUTION_ERRORS = (NoAccessPermissionError, HttpStatusError, UnSupportedTypeError, NotFoundError)


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


def format_manifest_lines(manifest: ResourceManifest) -> tuple[str, ...]:
    """Render the available video/audio streams without exposing signed media URLs."""
    rows: list[tuple[str, ...]] = []
    for video in manifest.videos:
        quality = video["quality"]
        quality_info = video_quality_map.get(quality)
        description = str(quality_info["description"]) if quality_info is not None else "Unknown"
        rows.append(
            (
                "video",
                str(quality),
                video["codec"],
                f"{video['width']}x{video['height']}",
                description,
            )
        )
    for audio in manifest.audios:
        quality = audio["quality"]
        quality_info = audio_quality_map.get(quality)
        description = str(quality_info["description"]) if quality_info is not None else "Unknown"
        rows.append(("audio", str(quality), audio["codec"], "-", description))

    if not rows:
        return ("没有可用的视频或音频流。",)
    return _render_table(("TYPE", "QUALITY", "CODEC", "RESOLUTION", "DESCRIPTION"), rows)


def _render_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> tuple[str, ...]:
    all_rows = (headers, *rows)
    widths = tuple(max(get_string_width(row[index]) for row in all_rows) for index in range(len(headers)))
    rendered: list[str] = []
    for row in all_rows:
        cells: list[str] = []
        for index, cell in enumerate(row):
            if index == len(row) - 1:
                cells.append(cell)
                continue
            cells.append(cell + " " * (widths[index] - get_string_width(cell)))
        rendered.append("  ".join(cells))
    return tuple(rendered)


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

                    items = tuple(item for _, item in iter_media_items(result.media))
                    for index, item in enumerate(items, start=1):
                        prefix = f"[{index}/{len(items)}] " if len(items) > 1 else ""
                        Logger.print(f"{prefix}{item.metadata.title}")
                        try:
                            manifest = await resolve_resource_manifest(scope, item, probe_request)
                        except _FORMAT_RESOLUTION_ERRORS as error:
                            emit_download_report(error.message, ReportLevel.ERROR)
                            Logger.print("")
                            continue

                        for line in format_manifest_lines(manifest):
                            Logger.print(line)
                        listed_streams = listed_streams or bool(manifest.videos or manifest.audios)
                        Logger.print("")

    if listed_streams:
        Logger.print("选择格式：视频使用 -q/--video-quality 和 --vcodec；音频使用 -aq/--audio-quality 和 --acodec。")
