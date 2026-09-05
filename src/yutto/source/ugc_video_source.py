from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from returns.result import Failure

from yutto.core.operation import emit_download_report
from yutto.exceptions import NoAccessPermissionError, NotFoundError
from yutto.media import UgcPage, UgcVideo
from yutto.source import Source
from yutto.types import AId, AvId, BvId, CId
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.metadata import ItemMetaData
from yutto.utils.time import get_time_stamp_by_now

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.source import SourceOptions


class UgcVideoSource(Source):
    id: AvId

    async def resolve(self, scope: ExecutionScope) -> UgcVideo:
        video_info = await self.get_ugc_video_info(scope, self.id)

        metadata: ItemMetaData | None = None
        if self.options.require_metadata:
            metadata = ItemMetaData(
                show_title=video_info["title"],
                plot=video_info["desc"],
                thumb=video_info["pic"],
                premiered=video_info["pubdate"],
                dateadded=get_time_stamp_by_now(),
                actors=self._parse_actors_info(video_info),
                genre=self._parse_genre_info(video_info),
                tag=await self.get_ugc_video_tag(scope, self.id),
                website=BvId(video_info["bvid"]).to_url(),
            )

        pages = [
            UgcPage(
                avid=self.id,
                cid=CId(item["cid"]),
                title=item["part"],
                extraMetaData=metadata,
                cover_url=video_info["pic"],
            )
            for item in self._select_items(video_info["pages"])
        ]
        return UgcVideo(avid=self.id, title=video_info["title"], items=pages)

    async def get_ugc_video_info(self, scope: ExecutionScope, avid: AvId) -> dict[str, Any]:
        api = f"https://api.bilibili.com/x/web-interface/view?{avid.to_param()}"
        res = await Fetcher.fetch_json(scope, api)
        if isinstance(res, Failure):
            raise NotFoundError(f"无法获取该视频 {avid} 信息") from res.failure()

        res_json = res.unwrap()
        res_json_data = res_json.get("data")
        if res_json["code"] == 62002:
            raise NotFoundError(f"无法下载该视频 {avid}，原因：{res_json['message']}")
        if res_json["code"] == 62012:
            raise NoAccessPermissionError(
                f"无法获取该视频 {avid} 信息，原因：{res_json['message']}（当前稿件up主设置为仅自见）"
            )
        if res_json["code"] == -404:
            raise NotFoundError(f"啊叻？视频 {avid} 不见了诶")
        assert res_json_data is not None, "响应数据无 data 域"

        if res_json_data.get("forward"):
            forward_avid = AId(res_json_data["forward"])
            emit_download_report(f"视频 {avid} 撞车了哦！正在跳转到原视频 {forward_avid}～")
            res_json_data = await self.get_ugc_video_info(scope, forward_avid)
            self.id = AId(res_json_data["aid"])
            return res_json_data

        return res_json_data

    async def get_ugc_video_tag(self, scope: ExecutionScope, avid: AvId) -> list[str]:
        api = f"https://api.bilibili.com/x/tag/archive/tags?{avid.to_param()}"
        res_json = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
        if res_json["code"] != 0:
            raise NotFoundError(f"无法获取视频 {avid} 标签")
        return [tag["tag_name"] for tag in res_json["data"]]


async def resolve_ugc_videos(
    scope: ExecutionScope,
    avids: list[AvId],
    options: SourceOptions,
) -> list[UgcVideo]:
    return list(
        await asyncio.gather(
            *(
                UgcVideoSource(id=avid, selection="1~-1", options=options).resolve(scope)
                for avid in avids
            )
        )
    )
