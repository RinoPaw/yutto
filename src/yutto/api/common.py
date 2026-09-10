from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.exceptions import NoAccessPermissionError, NotFoundError
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

NAV_API = "https://api.bilibili.com/x/web-interface/nav"


async def get_nav(scope: ExecutionScope) -> dict[str, Any]:
    if scope.nav_cache is not None:
        return scope.nav_cache
    async with scope.nav_lock:
        if scope.nav_cache is None:
            scope.nav_cache = unwrap_fetch_result(await Fetcher.fetch_json(scope, NAV_API))
        return scope.nav_cache


async def fetch_payload(
    scope: ExecutionScope,
    url: str,
    description: str,
    identifier: str,
    data_key: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if params is None:
        result = await Fetcher.fetch_json(scope, url)
    else:
        result = await Fetcher.fetch_json(scope, url, params=params)
    response = unwrap_fetch_result(result)
    if response.get("code") == -404:
        raise NotFoundError(f"未找到{description}（{identifier}）")
    payload = response.get(data_key)
    if payload is None:
        raise NoAccessPermissionError(f"无法解析{description}（{identifier}），原因：{response.get('message')}")
    return payload


__all__ = ["NAV_API", "fetch_payload", "get_nav"]
