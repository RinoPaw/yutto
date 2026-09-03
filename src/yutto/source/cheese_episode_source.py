from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.exceptions import NotFoundError
from yutto.media import CheeseEpisode, CheeseSeason
from yutto.source import Source
from yutto.types import EpisodeId, SeasonId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


def parse_cheese_episode(item: dict[str, Any], *, require_metadata: bool = False) -> CheeseEpisode:
    title = item["title"]
    metadata = None
    if require_metadata:
        metadata = ItemMetaData(
            show_title=title,
            plot=title,
            thumb=item["cover"],
            premiered=str(item["release_date"]),
        )
    return CheeseEpisode(
        id=EpisodeId(str(item["id"])),
        title=title,
        extraMetaData=metadata,
    )


class CheeseEpisodeSource(Source):
    id: EpisodeId

    async def resolve(self, scope: ExecutionScope) -> CheeseSeason:
        api = f"https://api.bilibili.com/pugv/view/web/season?ep_id={self.id}"
        res = await self._fetch_payload(scope, api, "该课程", f"episode_id: {self.id}", "data")

        item = next((entry for entry in res["episodes"] if entry["id"] == int(self.id.value)), None)
        if item is None:
            raise NotFoundError(f"无法在课程 {res['title']} 中找到剧集 ep{self.id}")

        season_id = res.get("season_id", self.id.value)
        return CheeseSeason(
            id=SeasonId(str(season_id)),
            title=str(res["title"]),
            items=[parse_cheese_episode(item, require_metadata=self.options.require_metadata)],
        )
