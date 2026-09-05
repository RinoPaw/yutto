from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.api.user_info import encode_wbi, get_wbi_img
from yutto.media import UgcSpace
from yutto.source import Source
from yutto.source.ugc_video_source import resolve_ugc_videos
from yutto.types import BvId, MId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


@dataclass(slots=True, kw_only=True)
class UgcSpaceSource(Source):
    id: MId

    async def resolve(self, scope: ExecutionScope) -> UgcSpace:
        wbi_img = await get_wbi_img(scope)
        profile = await self._fetch_payload(
            scope,
            "https://api.bilibili.com/x/space/wbi/acc/info",
            "UP 主",
            f"mid: {self.id}",
            "data",
            params=encode_wbi({"mid": self.id}, wbi_img),
        )
        payload = await self._fetch_payload(
            scope,
            "https://api.bilibili.com/x/space/wbi/arc/search",
            "UP 主空间",
            f"mid: {self.id}",
            "data",
            params=encode_wbi(
                {
                    "mid": self.id,
                    "ps": 30,
                    "tid": 0,
                    "pn": 1,
                    "order": "pubdate",
                },
                wbi_img,
            ),
        )
        archives: list[dict[str, Any]] = [
            item for item in payload.get("list", {}).get("vlist") or [] if item.get("bvid")
        ]
        selected_archives = self._select_items(archives)
        videos = await resolve_ugc_videos(
            scope,
            [BvId(item["bvid"]) for item in selected_archives],
            self.options,
        )
        return UgcSpace(
            mid=self.id,
            title=profile["name"],
            items=videos,
        )
