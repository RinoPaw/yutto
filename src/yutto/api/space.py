from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload
from yutto.auth.wbi import encode_wbi, get_wbi_img

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import MId


async def get_space_profile_and_archives(
    scope: ExecutionScope,
    mid: MId,
    *,
    stop_before_timestamp: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    wbi_img = await get_wbi_img(scope)
    profile = await fetch_payload(
        scope,
        "https://api.bilibili.com/x/space/wbi/acc/info",
        "UP 主",
        f"mid: {mid}",
        "data",
        params=encode_wbi({"mid": mid}, wbi_img),
    )

    page_size = 30
    page_num = 1
    archives: list[dict[str, Any]] = []
    while True:
        payload = await fetch_payload(
            scope,
            "https://api.bilibili.com/x/space/wbi/arc/search",
            "UP 主空间",
            f"mid: {mid}",
            "data",
            params=encode_wbi(
                {
                    "mid": mid,
                    "ps": page_size,
                    "tid": 0,
                    "pn": page_num,
                    "order": "pubdate",
                },
                wbi_img,
            ),
        )
        page_archives: list[dict[str, Any]] = payload.get("list", {}).get("vlist") or []
        archives.extend(item for item in page_archives if item.get("bvid"))

        if stop_before_timestamp is not None and any(
            item.get("created") is not None and int(item["created"]) < stop_before_timestamp for item in page_archives
        ):
            break

        total = payload.get("page", {}).get("count")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return profile, archives


__all__ = ["get_space_profile_and_archives"]
