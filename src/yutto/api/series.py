from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import MId, SeriesId


async def get_series_info(scope: ExecutionScope, series_id: SeriesId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/x/series/series?series_id={series_id}",
        "视频系列",
        f"series_id: {series_id}",
        "data",
    )


async def get_series_archives(scope: ExecutionScope, series_id: SeriesId, mid: MId) -> list[dict[str, Any]]:
    page_size = 30
    page_num = 1
    archives: list[dict[str, Any]] = []

    while True:
        payload = await fetch_payload(
            scope,
            (
                "https://api.bilibili.com/x/series/archives"
                f"?mid={mid}&series_id={series_id}&only_normal=true"
                f"&pn={page_num}&ps={page_size}"
            ),
            "视频系列",
            f"series_id: {series_id}",
            "data",
        )
        page_archives: list[dict[str, Any]] = payload.get("archives") or []
        archives.extend(item for item in page_archives if item.get("bvid"))

        total = payload.get("page", {}).get("total")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return archives


__all__ = ["get_series_archives", "get_series_info"]
