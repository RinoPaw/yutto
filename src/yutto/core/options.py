from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from yutto.selection import Selection, parse_selection
from yutto.utils.filter import PublicationTimeFilter

if TYPE_CHECKING:
    from yutto.core.request import DownloadRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceOptions:
    selection: Selection | None = None
    with_extra_episodes: bool = False
    skip_preview: bool = False
    fetch_tags: bool = False
    publication_time_filter: PublicationTimeFilter | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceOptions:
    video: bool = True
    audio: bool = True
    danmaku: bool = True
    subtitle: bool = True
    cover: bool = True
    chapter_info: bool = True
    ai_translation_language: str | None = None
    danmaku_format: Literal["xml", "ass", "protobuf"] = "ass"


DEFAULT_SOURCE_OPTIONS = SourceOptions()
DEFAULT_RESOURCE_OPTIONS = ResourceOptions()


def source_options_from_request(request: DownloadRequest) -> SourceOptions:
    expression = request.selection.expression
    publication_time_filter = None
    if request.selection.start_time is not None or request.selection.end_time is not None:
        publication_time_filter = PublicationTimeFilter.from_strings(
            request.selection.start_time,
            request.selection.end_time,
        )
    return SourceOptions(
        selection=parse_selection(expression) if expression is not None else None,
        with_extra_episodes=request.scope.with_extra_episodes,
        skip_preview=request.selection.skip_preview,
        fetch_tags=request.resources.metadata,
        publication_time_filter=publication_time_filter,
    )


def resource_options_from_request(request: DownloadRequest) -> ResourceOptions:
    resources = request.resources
    return ResourceOptions(
        video=resources.video,
        audio=resources.audio,
        danmaku=resources.danmaku,
        subtitle=resources.subtitle,
        cover=resources.cover,
        chapter_info=resources.chapter_info,
        ai_translation_language=resources.ai_translation_language,
        danmaku_format=request.danmaku.format,
    )


__all__ = [
    "DEFAULT_RESOURCE_OPTIONS",
    "DEFAULT_SOURCE_OPTIONS",
    "ResourceOptions",
    "SourceOptions",
    "resource_options_from_request",
    "source_options_from_request",
]
