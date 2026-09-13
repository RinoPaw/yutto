from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.exceptions import NotLoginError
from yutto.source import SourceOptions, UgcWatchLaterSource
from yutto.types import BilibiliId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

_SCOPE = cast("ExecutionScope", None)


@pytest.mark.api
@pytest.mark.parametrize("code", [-101, -400])
def test_watch_later_not_login_is_reported_as_source_failure(
    monkeypatch: pytest.MonkeyPatch,
    code: int,
) -> None:
    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": code, "message": "账号未登录"})

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    source = UgcWatchLaterSource(id=BilibiliId("watchlater"))

    result = asyncio.run(source.resolve(_SCOPE, SourceOptions()))

    assert result.media is None
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.index == 1
    assert failure.source == BilibiliId("watchlater")
    assert isinstance(failure.error, NotLoginError)
    assert failure.error.message == "账号未登录，无法获取稍后再看列表哦~ Ծ‸Ծ"
