from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcList, UgcVideo
from yutto.source import Source
from yutto.types import BilibiliId, BvId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcListSource(Source):
    """收藏夹、稍后再看等轻量列表来源。"""

    id: BilibiliId
    kind: str

    async def resolve(self, scope: ExecutionScope) -> UgcList:
        if self.kind == "watch_later":
            payload = await self._fetch_payload(
                scope,
                "https://api.bilibili.com/x/v2/history/toview/web",
                "稍后再看",
                "watch_later",
                "data",
            )
            items = payload.get("list", [])
            return UgcList(
                id=self.id,
                title="稍后再看",
                items=[
                    UgcVideo(id=BvId(item["bvid"]), title=str(item.get("title", "")))
                    for item in items
                    if item.get("bvid")
                ],
            )

        if self.kind == "favourite":
            info_api = f"https://api.bilibili.com/x/v3/fav/folder/info?media_id={self.id}"
            list_api = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={self.id}&pn=1&ps=20&platform=web"
            info = await self._fetch_payload(scope, info_api, "收藏夹", f"fid: {self.id}", "data")
            payload = await self._fetch_payload(scope, list_api, "收藏夹", f"fid: {self.id}", "data")
            medias: list[dict[str, Any]] = payload.get("medias") or []
            return UgcList(
                id=self.id,
                title=str(info.get("title", "")),
                items=[
                    UgcVideo(id=BvId(item["bvid"]), title=str(item.get("title", "")))
                    for item in medias
                    if item.get("bvid")
                ],
            )

        raise ValueError(f"未知的 UGC 列表类型：{self.kind}")
