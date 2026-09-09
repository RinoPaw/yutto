from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.exceptions import NoAccessPermissionError, NotFoundError
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


async def fetch_payload(
    scope: ExecutionScope,
    url: str,
    description: str,
    identifier: str,
    data_key: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = await Fetcher.fetch_json(scope, url) if params is None else await Fetcher.fetch_json(scope, url, params=params)
    response = unwrap_fetch_result(result)
    if response.get("code") == -404:
        raise NotFoundError(f"未找到{description}（{identifier}）")
    payload = response.get(data_key)
    if payload is None:
        raise NoAccessPermissionError(f"无法解析{description}（{identifier}），原因：{response.get('message')}")
    return payload


__all__ = ["fetch_payload"]
