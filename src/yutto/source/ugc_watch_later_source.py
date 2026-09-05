from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcWatchLater
from yutto.source import Source
from yutto.source.ugc_video_source import resolve_ugc_videos
from yutto.types import BvId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcWatchLaterSource(Source):
    async def resolve(self, scope: ExecutionScope) -> UgcWatchLater:
        payload = await self._fetch_payload(
            scope,
            "https://api.bilibili.com/x/v2/history/toview/web",
            "稍后再看",
            "watch_later",
            "data",
        )
        entries: list[dict[str, Any]] = [item for item in payload.get("list", []) if item.get("bvid")]
        selected_entries = self._select_items(entries)
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_entries],
            self.options,
        )
        return UgcWatchLater(title="稍后再看", items=videos)
