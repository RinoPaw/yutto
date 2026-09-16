from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from yutto.media.quality import audio_quality_map, video_quality_map

if TYPE_CHECKING:
    from yutto.downloader.selector import StreamSelection
    from yutto.resource import ResourceManifest

FormatSignature: TypeAlias = tuple[
    tuple[tuple[int, str, int, int, int], ...],
    tuple[tuple[int, str], ...],
]


def format_manifest_lines(
    manifest: ResourceManifest,
    selection: StreamSelection | None = None,
) -> tuple[str, ...]:
    """Render one manifest consistently for preview and download output."""
    selected_video_index = selection.video_index if selection is not None else None
    selected_audio_index = selection.audio_index if selection is not None else None
    lines: list[str] = []

    if not manifest.videos:
        lines.append("不包含任何视频流")
    else:
        lines.append(f"共包含以下 {len(manifest.videos)} 个视频流：")
        for index, video in enumerate(manifest.videos):
            quality_info = video_quality_map.get(video["quality"])
            description = str(quality_info["description"]) if quality_info is not None else "Unknown"
            lines.append(
                "{}{:2} [{:^4}] [{:>4}x{:<4}] <{:^8}> #{}".format(
                    "*" if index == selected_video_index else " ",
                    index,
                    video["codec"].upper(),
                    video["width"],
                    video["height"],
                    description,
                    len(video["mirrors"]) + 1,
                )
            )

    if not manifest.audios:
        lines.append("不包含任何音频流")
    else:
        lines.append(f"共包含以下 {len(manifest.audios)} 个音频流：")
        for index, audio in enumerate(manifest.audios):
            quality_info = audio_quality_map.get(audio["quality"])
            description = str(quality_info["description"]) if quality_info is not None else "Unknown"
            lines.append(
                "{}{:2} [{:^4}] <{:^8}>".format(
                    "*" if index == selected_audio_index else " ",
                    index,
                    audio["codec"].upper(),
                    description,
                )
            )

    return tuple(lines)


def manifest_format_signature(manifest: ResourceManifest) -> FormatSignature:
    """Return a stable displayed-format signature while ignoring signed URLs."""
    videos = tuple(
        sorted(
            (
                video["quality"],
                video["codec"],
                video["width"],
                video["height"],
                len(video["mirrors"]),
            )
            for video in manifest.videos
        )
    )
    audios = tuple(sorted((audio["quality"], audio["codec"]) for audio in manifest.audios))
    return videos, audios
