from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.exceptions import NoAccessPermissionError, NotFoundError, NotLoginError
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

WATCH_LATER_API = "https://api.bilibili.com/x/v2/history/toview/web"


async def get_watch_later_entries(scope: ExecutionScope) -> list[dict[str, Any]]:
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, WATCH_LATER_API))
    if response.get("code") in {-101, -400}:
        raise NotLoginError("账号未登录，无法获取稍后再看列表哦~ Ծ‸Ծ")
    if response.get("code") == -404:
        raise NotFoundError("未找到稍后再看（watch_later）")
    payload = response.get("data")
    if payload is None:
        raise NoAccessPermissionError(f"无法解析稍后再看（watch_later），原因：{response.get('message')}")
    return [item for item in payload.get("list", []) if item.get("bvid")]


__all__ = ["WATCH_LATER_API", "get_watch_later_entries"]
