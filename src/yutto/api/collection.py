from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import CollectionId, MId


async def get_collection(
    scope: ExecutionScope,
    collection_id: CollectionId,
    owner_id: MId,
) -> tuple[str, list[dict[str, Any]]]:
    page_size = 30
    page_num = 1
    archives: list[dict[str, Any]] = []
    title = ""

    while True:
        payload = await fetch_payload(
            scope,
            (
                "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
                f"?mid={owner_id}&season_id={collection_id}&sort_reverse=false"
                f"&page_num={page_num}&page_size={page_size}"
            ),
            "视频合集",
            f"collection_id: {collection_id}",
            "data",
        )
        if page_num == 1:
            title = str(payload.get("meta", {}).get("name", ""))

        page_archives: list[dict[str, Any]] = payload.get("archives") or []
        archives.extend(item for item in page_archives if item.get("bvid"))

        total = payload.get("page", {}).get("total")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return title, archives


__all__ = ["get_collection"]
