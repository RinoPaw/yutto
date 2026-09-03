from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.exceptions import NotFoundError
from yutto.media import BangumiEpisode, BangumiSeason
from yutto.source import Source
from yutto.types import EpisodeId, SeasonId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


def bangumi_episode_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = list(result["episodes"])
    for section in result.get("section", []):
        if section["type"] != 5:
            items += section["episodes"]
    return items


def parse_bangumi_episode(item: dict[str, Any], *, require_metadata: bool = False) -> BangumiEpisode:
    long_title = item["long_title"]
    title = f"{item['title']} {long_title}" if long_title else item["title"]
    metadata = None
    if require_metadata:
        metadata = ItemMetaData(
            show_title=item["share_copy"],
            plot=item["share_copy"],
            thumb=item["cover"],
            premiered=str(item["pub_time"]),
        )
    return BangumiEpisode(
        id=EpisodeId(str(item["id"])),
        title=title,
        extraMetaData=metadata,
    )


class BangumiEpisodeSource(Source):
    id: EpisodeId

    async def resolve(self, scope: ExecutionScope) -> BangumiSeason:
        api = f"https://api.bilibili.com/pgc/view/web/season?ep_id={self.id}"
        res = await self._fetch_payload(scope, api, "该番剧", f"episode_id: {self.id}", "result")

        item = next((entry for entry in bangumi_episode_items(res) if entry["id"] == int(self.id.value)), None)
        if item is None:
            raise NotFoundError(f"未找到该番剧中的剧集（episode_id: {self.id}）")

        return BangumiSeason(
            id=SeasonId(str(res["season_id"])),
            title=str(res["title"]),
            items=[parse_bangumi_episode(item, require_metadata=self.options.require_metadata)],
        )
