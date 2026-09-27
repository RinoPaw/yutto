from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.api.season import get_bangumi_season, get_cheese_season, get_season_id_by_media
from yutto.exceptions import NoAccessPermissionError, NotFoundError
from yutto.types import MediaId, SeasonId
from yutto.utils.fetcher import Fetcher

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

_SCOPE = cast("ExecutionScope", None)


def test_bangumi_source_rejects_non_mapping_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": 0, "message": "0", "result": []})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NoAccessPermissionError, match="API 响应格式异常"):
        asyncio.run(get_bangumi_season(_SCOPE, SeasonId("1")))


def test_bangumi_source_requires_episode_list(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": 0, "message": "0", "result": {}})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NotFoundError, match="响应缺少剧集列表"):
        asyncio.run(get_bangumi_season(_SCOPE, SeasonId("1")))


def test_cheese_source_requires_episode_list(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": 0, "message": "0", "data": {}})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NotFoundError, match="响应缺少剧集列表"):
        asyncio.run(get_cheese_season(_SCOPE, SeasonId("1")))


def test_media_id_source_requires_season_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": 0, "message": "0", "result": {"media": {}}})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NotFoundError, match="响应缺少 season_id"):
        asyncio.run(get_season_id_by_media(_SCOPE, MediaId("1")))
