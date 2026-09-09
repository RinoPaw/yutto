from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


async def get_watch_later_entries(scope: ExecutionScope) -> list[dict[str, Any]]:
    payload = await fetch_payload(
        scope,
        "https://api.bilibili.com/x/v2/history/toview/web",
        "稍后再看",
        "watch_later",
        "data",
    )
    return [item for item in payload.get("list", []) if item.get("bvid")]


__all__ = ["get_watch_later_entries"]
