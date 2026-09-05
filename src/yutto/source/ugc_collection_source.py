from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcCollection
from yutto.source import Source
from yutto.source.ugc_video_source import resolve_ugc_videos
from yutto.types import BvId, CollectionId, MId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcCollectionSource(Source):
    id: CollectionId
    owner_id: MId

    async def resolve(self, scope: ExecutionScope) -> UgcCollection:
        list_api = (
            "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
            f"?mid={self.owner_id}&season_id={self.id}&sort_reverse=false&page_num=1&page_size=30"
        )
        payload = await self._fetch_payload(scope, list_api, "视频合集", f"collection_id: {self.id}", "data")
        archives: list[dict[str, Any]] = [item for item in payload.get("archives") or [] if item.get("bvid")]
        selected_archives = self._select_items(archives)
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_archives],
            self.options,
        )
        return UgcCollection(
            collection_id=self.id,
            title=payload.get("meta", {}).get("name", ""),
            items=videos,
        )
