from __future__ import annotations

from typing import Any, cast

import pytest
from returns.result import Success

from yutto.core.input import parse_input
from yutto.core.request import DownloadRequest
from yutto.exceptions import WrongUrlError
from yutto.source import UgcVideoSource
from yutto.utils.fetcher import Fetcher
from yutto.utils.functional import as_sync

pytestmark = pytest.mark.processor


@as_sync
async def test_parse_input_prefers_pure_parser(monkeypatch: pytest.MonkeyPatch):
    async def fail_redirect(*args: Any, **kwargs: Any):
        pytest.fail("redirect must not be requested for directly parseable inputs")

    monkeypatch.setattr(Fetcher, "get_redirected_url", staticmethod(fail_redirect))
    request = DownloadRequest.model_validate({"source": {"url": "BV1D84y1t76J"}})

    parsed_input = await parse_input(cast(Any, object()), request)

    assert parsed_input.value == "BV1D84y1t76J"
    assert isinstance(parsed_input.source, UgcVideoSource)
    assert parsed_input.source.page is None


@as_sync
async def test_parse_input_redirects_only_after_parse_miss(monkeypatch: pytest.MonkeyPatch):
    async def fake_redirect(scope: Any, value: str):
        assert value == "https://b23.tv/opaque"
        return Success("https://www.bilibili.com/video/BV1D84y1t76J?p=2")

    monkeypatch.setattr(Fetcher, "get_redirected_url", staticmethod(fake_redirect))
    request = DownloadRequest.model_validate({"source": {"url": "https://b23.tv/opaque"}})

    parsed_input = await parse_input(cast(Any, object()), request)

    assert parsed_input.value == "https://www.bilibili.com/video/BV1D84y1t76J?p=2"
    assert isinstance(parsed_input.source, UgcVideoSource)
    assert parsed_input.source.page == 2


@as_sync
async def test_parse_input_does_not_attach_request_options(monkeypatch: pytest.MonkeyPatch):
    async def fail_redirect(*args: Any, **kwargs: Any):
        pytest.fail("redirect must not be requested for directly parseable inputs")

    monkeypatch.setattr(Fetcher, "get_redirected_url", staticmethod(fail_redirect))
    request = DownloadRequest.model_validate(
        {
            "source": {"url": "BV1D84y1t76J"},
            "scope": {"with_extra_episodes": True},
            "selection": {"episodes": "3", "skip_preview": True},
            "resources": {"metadata": True},
        }
    )

    parsed_input = await parse_input(cast(Any, object()), request)
    source = parsed_input.source

    assert isinstance(source, UgcVideoSource)
    assert source.page is None
    assert not hasattr(source, "options")


@as_sync
async def test_parse_input_rejects_unrecognized_redirect_target(monkeypatch: pytest.MonkeyPatch):
    async def fake_redirect(scope: Any, value: str):
        return Success("https://example.com/not-bilibili")

    monkeypatch.setattr(Fetcher, "get_redirected_url", staticmethod(fake_redirect))
    request = DownloadRequest.model_validate({"source": {"url": "https://b23.tv/opaque"}})

    with pytest.raises(WrongUrlError, match="无法识别"):
        await parse_input(cast(Any, object()), request)
