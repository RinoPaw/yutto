from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcCollection, UgcVideo
from yutto.source import Source
from yutto.types import BvId, CollectionId, MId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcCollectionSource(Source):
    id: CollectionId
    owner_id: MId

    async def resolve(self, scope: ExecutionScope) -> UgcCollection:
        info_api = f"https://api.bilibili.com/x/polymer/web-space/seasons_series_detail?season_id={self.id}"
        list_api = (
            "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
            f"?mid={self.owner_id}&season_id={self.id}&sort_reverse=false&page_num=1&page_size=30"
        )
        info = await self._fetch_payload(scope, info_api, "视频合集", f"collection_id: {self.id}", "data")
        payload = await self._fetch_payload(scope, list_api, "视频合集", f"collection_id: {self.id}", "data")
        archives: list[dict[str, Any]] = payload.get("archives") or []
        return UgcCollection(
            id=self.id,
            title=str(info.get("meta", {}).get("name", "")),
            items=[
                UgcVideo(id=BvId(item["bvid"]), title=str(item.get("title", "")))
                for item in archives
                if item.get("bvid")
            ],
        )
