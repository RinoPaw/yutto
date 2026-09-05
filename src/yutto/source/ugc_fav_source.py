from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcFav
from yutto.source import Source
from yutto.source.ugc_video_source import resolve_ugc_videos
from yutto.types import BvId, FId

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
        medias: list[dict[str, Any]] = [item for item in payload.get("medias") or [] if item.get("bvid")]
        selected_medias = self._select_items(medias)
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_medias],
            self.options,
        )
        return UgcFav(
            fid=self.id,
            title=info.get("title", ""),
            items=videos,
        )
