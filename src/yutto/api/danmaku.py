from __future__ import annotations

from typing import TYPE_CHECKING

from biliass import get_danmaku_meta_size

from yutto.exceptions import NoAccessPermissionError
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AId, CId


def get_xml_danmaku_url(cid: CId) -> str:
    return f"http://comment.bilibili.com/{cid}.xml"


async def get_protobuf_danmaku_urls(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
) -> tuple[str, ...]:
    meta = unwrap_fetch_result(
        await Fetcher.fetch_bin(
            scope,
            f"https://api.bilibili.com/x/v2/dm/web/view?type=1&oid={cid}&pid={aid.value}",
        )
    )
    if meta is None:
        raise NoAccessPermissionError(f"无法获取该视频弹幕元数据（{aid}, cid: {cid}）")

    size = get_danmaku_meta_size(meta)
    return tuple(
        f"http://api.bilibili.com/x/v2/dm/web/seg.so?type=1&oid={cid}&segment_index={segment_id}"
        for segment_id in range(1, size + 1)
    )


__all__ = [
    "get_protobuf_danmaku_urls",
    "get_xml_danmaku_url",
]
