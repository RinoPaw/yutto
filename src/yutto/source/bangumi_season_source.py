from __future__ import annotations

from typing import TYPE_CHECKING

from yutto.media import BangumiSeason
from yutto.source import Source
from yutto.source.bangumi_episode_source import bangumi_episode_items, parse_bangumi_episode
from yutto.types import MediaId, SeasonId
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


class BangumiSeasonSource(Source):
    id: SeasonId | MediaId

    async def resolve(self, scope: ExecutionScope) -> BangumiSeason:
        if isinstance(self.id, MediaId):
            self.id = await self._get_season_id(scope, self.id)
        elif isinstance(self.id, SeasonId):
            self.id = self.id

        api = f"https://api.bilibili.com/pgc/view/web/season?season_id={self.id}"
        res = await self._fetch_payload(scope, api, "该番剧列表", f"season_id: {self.id}", "result")

        return BangumiSeason(
            id=self.id,
            title=str(res["title"]),
            items=[
                parse_bangumi_episode(item, require_metadata=self.options.require_metadata)
                for item in bangumi_episode_items(res)
            ],
        )

    @staticmethod
    async def _get_season_id(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
        media_api = f"https://api.bilibili.com/pgc/review/user?media_id={media_id}"
        res_json = unwrap_fetch_result(await Fetcher.fetch_json(scope, media_api))
        return SeasonId(str(res_json["result"]["media"]["season_id"]))
