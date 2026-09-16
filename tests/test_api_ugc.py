from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.api.ugc import get_ugc_video_info
from yutto.exceptions import NotFoundError
from yutto.types import BvId
from yutto.utils.fetcher import Fetcher

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


def test_ugc_video_info_without_data_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(*_args: Any, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success({"code": -400, "message": "请求错误"})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    with pytest.raises(NotFoundError, match="无法获取该视频 BV1001 信息，原因：请求错误"):
        asyncio.run(
            get_ugc_video_info(
                cast("ExecutionScope", None),
                BvId("BV1001"),
            )
        )
