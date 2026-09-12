from __future__ import annotations

from typing import TYPE_CHECKING

from biliass import get_danmaku_meta_size

from yutto.exceptions import NoAccessPermissionError
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AId, CId


async def get_danmaku_segment_count(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
) -> int:
    meta = unwrap_fetch_result(
        await Fetcher.fetch_bin(
            scope,
            f"https://api.bilibili.com/x/v2/dm/web/view?type=1&oid={cid}&pid={aid.value}",
        )
    )
    if meta is None:
        raise NoAccessPermissionError(f"无法获取该视频弹幕元数据（{aid}, cid: {cid}）")
    return get_danmaku_meta_size(meta)


__all__ = ["get_danmaku_segment_count"]
