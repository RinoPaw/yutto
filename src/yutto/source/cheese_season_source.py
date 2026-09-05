from __future__ import annotations

from typing import TYPE_CHECKING

from yutto.media import CheeseSeason
from yutto.source import Source
from yutto.source.cheese_episode_source import parse_cheese_episode

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import SeasonId


class CheeseSeasonSource(Source):
    id: SeasonId

    async def resolve(self, scope: ExecutionScope) -> CheeseSeason:
        api = f"https://api.bilibili.com/pugv/view/web/season?season_id={self.id}"
        res = await self._fetch_payload(scope, api, "该课程列表", f"season_id: {self.id}", "data")
        episode_items = self._select_items(res["episodes"])

        return CheeseSeason(
            season_id=self.id,
            title=res["title"],
            items=[
                parse_cheese_episode(item, require_metadata=self.options.require_metadata)
                for item in episode_items
            ],
        )
