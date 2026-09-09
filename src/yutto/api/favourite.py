from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import FId, MId


async def get_favourite_info(scope: ExecutionScope, fid: FId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/x/v3/fav/folder/info?media_id={fid}",
        "收藏夹",
        f"fid: {fid}",
        "data",
    )


async def get_favourite_medias(scope: ExecutionScope, fid: FId) -> list[dict[str, Any]]:
    page_size = 20
    page_num = 1
    medias: list[dict[str, Any]] = []

    while True:
        payload = await fetch_payload(
            scope,
            f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fid}&pn={page_num}&ps={page_size}&platform=web",
            "收藏夹",
            f"fid: {fid}",
            "data",
        )
        page_medias: list[dict[str, Any]] = payload.get("medias") or []
        medias.extend(item for item in page_medias if item.get("bvid"))

        has_more = payload.get("has_more")
        if has_more is not None:
            if not has_more:
                break
        elif len(page_medias) < page_size:
            break
        page_num += 1

    return medias


async def get_all_favourite_folders(scope: ExecutionScope, mid: MId) -> list[dict[str, Any]]:
    api = f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={mid}"
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
    data = response.get("data") or {}
    return list(data.get("list") or [])


__all__ = ["get_all_favourite_folders", "get_favourite_info", "get_favourite_medias"]
