from __future__ import annotations

import dataclasses

import pytest

from yutto.core.options import (
    ResourceOptions,
    SourceOptions,
    resource_options_from_request,
    source_options_from_request,
)
from yutto.core.request import DownloadRequest
from yutto.selection import Selection


def test_internal_options_have_no_field_defaults() -> None:
    for options_type in (SourceOptions, ResourceOptions):
        assert all(field.default is dataclasses.MISSING for field in dataclasses.fields(options_type))
        assert all(field.default_factory is dataclasses.MISSING for field in dataclasses.fields(options_type))

    with pytest.raises(TypeError):
        SourceOptions()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        ResourceOptions()  # type: ignore[call-arg]


def test_request_defaults_are_projected_once_into_internal_options() -> None:
    request = DownloadRequest.model_validate({"source": {"url": "BV1D84y1t76J"}})

    source_options = source_options_from_request(request)
    resource_options = resource_options_from_request(request)

    assert source_options == SourceOptions(
        selection=None,
        with_extra_episodes=False,
        skip_preview=False,
        require_metadata=False,
    )
    assert resource_options == ResourceOptions(
        video=True,
        audio=True,
        danmaku=True,
        subtitle=True,
        metadata=False,
        cover=True,
        chapter_info=True,
        ai_translation_language=None,
        danmaku_format="ass",
    )


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
