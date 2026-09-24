from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.exceptions import NotLoginError
from yutto.scope import Scope
from yutto.source import UgcWatchLaterSource

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

_EXECUTION = cast("ExecutionScope", None)


@pytest.mark.api
@pytest.mark.parametrize("code", [-101, -400])
def test_watch_later_not_login_propagates_root_source_failure(
    monkeypatch: pytest.MonkeyPatch,
    code: int,
) -> None:
    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": code, "message": "账号未登录"})

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    source = UgcWatchLaterSource()

    with pytest.raises(NotLoginError) as raised:
        asyncio.run(source.resolve(_EXECUTION, Scope()))

    assert raised.value.message == "账号未登录，无法获取稍后再看列表哦~ Ծ‸Ծ"
