from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto.media import UgcVideo, UgcWatchLater
from yutto.source import Source
from yutto.types import BilibiliId, BvId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcWatchLaterSource(Source):
    id: BilibiliId

    async def resolve(self, scope: ExecutionScope) -> UgcWatchLater:
        payload = await self._fetch_payload(
            scope,
            "https://api.bilibili.com/x/v2/history/toview/web",
            "稍后再看",
            "watch_later",
            "data",
        )
        return UgcWatchLater(
            id=self.id,
            items=[
                UgcVideo(id=BvId(item["bvid"]), title=str(item.get("title", "")))
                for item in payload.get("list", [])
                if item.get("bvid")
            ],
        )
