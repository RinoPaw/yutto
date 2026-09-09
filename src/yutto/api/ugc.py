from __future__ import annotations

from typing import TYPE_CHECKING, Any

from returns.result import Failure

from yutto.core.operation import emit_download_report
from yutto.exceptions import NoAccessPermissionError, NotFoundError
from yutto.types import AId
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AvId


async def get_ugc_video_info(scope: ExecutionScope, avid: AvId) -> tuple[AvId, dict[str, Any]]:
    api = f"https://api.bilibili.com/x/web-interface/view?{avid.to_param()}"
    result = await Fetcher.fetch_json(scope, api)
    if isinstance(result, Failure):
        raise NotFoundError(f"无法获取该视频 {avid} 信息") from result.failure()

    response = result.unwrap()
    data = response.get("data")
    if response["code"] == 62002:
        raise NotFoundError(f"无法下载该视频 {avid}，原因：{response['message']}")
    if response["code"] == 62012:
        raise NoAccessPermissionError(
            f"无法获取该视频 {avid} 信息，原因：{response['message']}（当前稿件UP主设置为仅自己可见）"
        )
    if response["code"] == -404:
        raise NotFoundError(f"哔咔！视频 {avid} 不见了诶")
    assert data is not None, "响应数据无 data 域"

    if data.get("forward"):
        forward_avid = AId(data["forward"])
        emit_download_report(f"视频 {avid} 撞车了哦！正在跳转到原视频 {forward_avid}～")
        return await get_ugc_video_info(scope, forward_avid)

    return avid, data


async def get_ugc_video_tags(scope: ExecutionScope, avid: AvId) -> list[str]:
    api = f"https://api.bilibili.com/x/tag/archive/tags?{avid.to_param()}"
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
    if response["code"] != 0:
        raise NotFoundError(f"无法获取视频 {avid} 标签")
    return [tag["tag_name"] for tag in response["data"]]


__all__ = ["get_ugc_video_info", "get_ugc_video_tags"]
