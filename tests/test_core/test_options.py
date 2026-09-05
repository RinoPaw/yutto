from __future__ import annotations

from yutto.core.options import (
    DEFAULT_RESOURCE_OPTIONS,
    DEFAULT_SOURCE_OPTIONS,
    ResourceOptions,
    SourceOptions,
    resource_options_from_request,
    source_options_from_request,
)
from yutto.core.request import DownloadRequest
from yutto.selection import Selection


def test_internal_options_define_canonical_defaults() -> None:
    assert SourceOptions() == DEFAULT_SOURCE_OPTIONS
    assert ResourceOptions() == DEFAULT_RESOURCE_OPTIONS


def test_request_defaults_follow_internal_defaults() -> None:
    request = DownloadRequest.model_validate({"source": {"url": "BV1D84y1t76J"}})

    assert request.scope.with_extra_episodes == DEFAULT_SOURCE_OPTIONS.with_extra_episodes
    assert request.selection.skip_preview == DEFAULT_SOURCE_OPTIONS.skip_preview
    assert request.resources.video == DEFAULT_RESOURCE_OPTIONS.video
    assert request.resources.audio == DEFAULT_RESOURCE_OPTIONS.audio
    assert request.resources.danmaku == DEFAULT_RESOURCE_OPTIONS.danmaku
    assert request.resources.subtitle == DEFAULT_RESOURCE_OPTIONS.subtitle
    assert request.resources.metadata == DEFAULT_RESOURCE_OPTIONS.metadata
    assert request.resources.cover == DEFAULT_RESOURCE_OPTIONS.cover
    assert request.resources.chapter_info == DEFAULT_RESOURCE_OPTIONS.chapter_info
    assert request.resources.ai_translation_language == DEFAULT_RESOURCE_OPTIONS.ai_translation_language
    assert request.danmaku.format == DEFAULT_RESOURCE_OPTIONS.danmaku_format

    assert source_options_from_request(request) == DEFAULT_SOURCE_OPTIONS
    assert resource_options_from_request(request) == DEFAULT_RESOURCE_OPTIONS


def test_source_selection_is_parsed_at_request_boundary() -> None:
    request = DownloadRequest.model_validate(
        {
            "source": {"url": "BV1D84y1t76J"},
            "selection": {"episodes": "3, 1~-1"},
        }
    )

    options = source_options_from_request(request)

    assert isinstance(options.selection, Selection)
    assert options.selection.resolve(4) == (3, 1, 2, 3, 4)
