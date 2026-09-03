from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcSeries, UgcVideo
from yutto.source import Source
from yutto.types import BvId, MId, SeriesId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcSeriesSource(Source):
    id: SeriesId
    owner_id: MId

    async def resolve(self, scope: ExecutionScope) -> UgcSeries:
        info_api = f"https://api.bilibili.com/x/v1/medialist/info?type=5&biz_id={self.id}"
        list_api = (
            "https://api.bilibili.com/x/series/archives"
            f"?mid={self.owner_id}&series_id={self.id}&only_normal=true&pn=1&ps=30"
        )
        info = await self._fetch_payload(scope, info_api, "视频系列", f"series_id: {self.id}", "data")
        payload = await self._fetch_payload(scope, list_api, "视频系列", f"series_id: {self.id}", "data")
        archives: list[dict[str, Any]] = payload.get("archives") or []
        return UgcSeries(
            id=self.id,
            title=str(info.get("title", "")),
            items=[
                UgcVideo(id=BvId(item["bvid"]), title=str(item.get("title", "")))
                for item in archives
                if item.get("bvid")
            ],
        )
