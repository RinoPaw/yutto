from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from yutto.selection import Selection, parse_selection

if TYPE_CHECKING:
    from yutto.core.request import DownloadRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceOptions:
    selection: Selection | None
    with_extra_episodes: bool
    skip_preview: bool
    require_metadata: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceOptions:
    video: bool
    audio: bool
    danmaku: bool
    subtitle: bool
    metadata: bool
    cover: bool
    chapter_info: bool
    ai_translation_language: str | None
    danmaku_format: Literal["xml", "ass", "protobuf"]


def source_options_from_request(request: DownloadRequest) -> SourceOptions:
    expression = request.selection.episodes
    return SourceOptions(
        selection=parse_selection(expression) if expression is not None else None,
        with_extra_episodes=request.scope.with_extra_episodes,
        skip_preview=request.selection.skip_preview,
        require_metadata=request.resources.metadata,
    )


def resource_options_from_request(request: DownloadRequest) -> ResourceOptions:
    resources = request.resources
    return ResourceOptions(
        video=resources.video,
        audio=resources.audio,
        danmaku=resources.danmaku,
        subtitle=resources.subtitle,
        metadata=resources.metadata,
        cover=resources.cover,
        chapter_info=resources.chapter_info,
        ai_translation_language=resources.ai_translation_language,
        danmaku_format=request.danmaku.format,
    )


__all__ = [
    "ResourceOptions",
    "SourceOptions",
    "resource_options_from_request",
    "source_options_from_request",
]
