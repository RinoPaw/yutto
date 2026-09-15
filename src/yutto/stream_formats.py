from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from yutto.media.quality import audio_quality_map, video_quality_map
from yutto.utils.console.formatter import get_string_width

if TYPE_CHECKING:
    from yutto.downloader.selector import StreamSelection
    from yutto.resource import ResourceManifest

FormatSignature: TypeAlias = tuple[
    tuple[tuple[int, str, int, int], ...],
    tuple[tuple[int, str], ...],
]


def format_manifest_lines(
    manifest: ResourceManifest,
    selection: StreamSelection | None = None,
) -> tuple[str, ...]:
    """Render one manifest consistently for listing and download output."""
    rows: list[tuple[str, ...]] = []
    selected_video_index = selection.video_index if selection is not None else None
    selected_audio_index = selection.audio_index if selection is not None else None

    for index, video in enumerate(manifest.videos):
        quality = video["quality"]
        quality_info = video_quality_map.get(quality)
        description = str(quality_info["description"]) if quality_info is not None else "Unknown"
        rows.append(
            (
                "*" if index == selected_video_index else "",
                "video",
                str(quality),
                video["codec"],
                f"{video['width']}x{video['height']}",
                description,
            )
        )
    for index, audio in enumerate(manifest.audios):
        quality = audio["quality"]
        quality_info = audio_quality_map.get(quality)
        description = str(quality_info["description"]) if quality_info is not None else "Unknown"
        rows.append(
            (
                "*" if index == selected_audio_index else "",
                "audio",
                str(quality),
                audio["codec"],
                "-",
                description,
            )
        )

    if not rows:
        return ("没有可用的视频或音频流。",)
    return _render_table(("SELECT", "TYPE", "QUALITY", "CODEC", "RESOLUTION", "DESCRIPTION"), rows)


def manifest_format_signature(manifest: ResourceManifest) -> FormatSignature:
    """Return a stable stream signature that intentionally ignores signed URLs and mirrors."""
    videos = tuple(
        sorted((video["quality"], video["codec"], video["width"], video["height"]) for video in manifest.videos)
    )
    audios = tuple(sorted((audio["quality"], audio["codec"]) for audio in manifest.audios))
    return videos, audios


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
