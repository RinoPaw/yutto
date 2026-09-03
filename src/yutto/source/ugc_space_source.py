from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.media import UgcSpace, UgcVideo
from yutto.source import Source
from yutto.types import BvId, MId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcSpaceSource(Source):
    id: MId

    async def resolve(self, scope: ExecutionScope) -> UgcSpace:
        api = (
            "https://api.bilibili.com/x/space/wbi/arc/search"
            f"?mid={self.id}&pn=1&ps=30"
        )
        payload = await self._fetch_payload(scope, api, "UP 主空间", f"mid: {self.id}", "data")
        archives: list[dict[str, Any]] = payload.get("list", {}).get("vlist") or []
        return UgcSpace(
            id=self.id,
            items=[
                UgcVideo(id=BvId(item["bvid"]), title=str(item.get("title", "")))
                for item in archives
                if item.get("bvid")
            ],
        )
