from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.api.ugc import (
    get_all_favourite_folders,
    get_ugc_video_info,
    get_ugc_video_tags,
    get_watch_later_entries,
)
from yutto.exceptions import NoAccessPermissionError, NotFoundError
from yutto.types import AId, BvId, MId
from yutto.utils.fetcher import Fetcher

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

_SCOPE = cast("ExecutionScope", None)


def test_ugc_video_info_without_data_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": -400, "message": "请求错误"})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NotFoundError, match="无法获取该视频 BV1001 信息，原因：请求错误"):
        asyncio.run(get_ugc_video_info(_SCOPE, BvId("BV1001")))


def test_ugc_video_info_without_aid_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": 0, "message": "0", "data": {}})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NotFoundError, match="API 响应缺少 aid"):
        asyncio.run(get_ugc_video_info(_SCOPE, BvId("BV1D84y1t76J")))


def test_ugc_video_tags_reject_malformed_data(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": 0, "message": "0", "data": {}})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NotFoundError, match="API 响应格式异常"):
        asyncio.run(get_ugc_video_tags(_SCOPE, AId("1")))


def test_all_favourite_folders_without_payload_raises_business_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": -400, "message": "请求错误"})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NoAccessPermissionError, match="无法解析收藏夹列表"):
        asyncio.run(get_all_favourite_folders(_SCOPE, MId("1")))


def test_watch_later_rejects_malformed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": 0, "message": "0", "data": {"list": {}}})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NoAccessPermissionError, match="API 响应格式异常"):
        asyncio.run(get_watch_later_entries(_SCOPE))
