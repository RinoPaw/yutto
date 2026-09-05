from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcSeries
from yutto.source import Source
from yutto.source.ugc_video_source import resolve_ugc_videos
from yutto.types import BvId, MId, SeriesId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcSeriesSource(Source):
    id: SeriesId

    async def resolve(self, scope: ExecutionScope) -> UgcSeries:
        info_api = f"https://api.bilibili.com/x/series/series?series_id={self.id}"
        info = await self._fetch_payload(scope, info_api, "视频系列", f"series_id: {self.id}", "data")
        meta = info.get("meta", {})
        mid = MId(str(meta["mid"]))  # API 返回 num；MId 当前要求 str

        list_api = (
            "https://api.bilibili.com/x/series/archives"
            f"?mid={mid}&series_id={self.id}&only_normal=true&pn=1&ps=30"
        )
        payload = await self._fetch_payload(scope, list_api, "视频系列", f"series_id: {self.id}", "data")
        archives: list[dict[str, Any]] = [item for item in payload.get("archives") or [] if item.get("bvid")]
        selected_archives = self._select_items(archives)
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_archives],
            self.options,
        )
        return UgcSeries(
            series_id=self.id,
            title=meta.get("name", ""),
            items=videos,
        )
