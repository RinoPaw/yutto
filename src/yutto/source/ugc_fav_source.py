from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcFav, UgcVideo
from yutto.source import Source
from yutto.types import FId, BvId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcFavSource(Source):
    id: FId

    async def resolve(self, scope: ExecutionScope) -> UgcFav:
        info_api = f"https://api.bilibili.com/x/v3/fav/folder/info?media_id={self.id}"
        list_api = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={self.id}&pn=1&ps=20&platform=web"
        info = await self._fetch_payload(scope, info_api, "收藏夹", f"fid: {self.id}", "data")
        payload = await self._fetch_payload(scope, list_api, "收藏夹", f"fid: {self.id}", "data")
        medias: list[dict[str, Any]] = payload.get("medias") or []
        return UgcFav(
            id=self.id,
            title=str(info.get("title", "")),
            items=[
                UgcVideo(id=BvId(item["bvid"]), title=str(item.get("title", "")))
                for item in medias
                if item.get("bvid")
            ],
        )
