from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.media import BangumiSeason
from yutto.source import Source
from yutto.source.bangumi_episode_source import parse_bangumi_episode
from yutto.types import MediaId, SeasonId
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


class BangumiSeasonSource(Source):
    id: SeasonId | MediaId

    async def resolve(self, scope: ExecutionScope) -> BangumiSeason:
        season_id = (
            await self._get_season_id(scope, self.id)
            if isinstance(self.id, MediaId)
            else self.id
        )
        api = f"https://api.bilibili.com/pgc/view/web/season?season_id={season_id}"
        res = await self._fetch_payload(scope, api, "该番剧列表", f"season_id: {season_id}", "result")

        episode_items: list[dict[str, Any]] = list(res["episodes"])
        if self.options.with_extra_episodes:
            for section in res.get("section", []):
                if section["type"] != 5:
                    episode_items.extend(section["episodes"])
        if self.options.skip_preview:
            episode_items = [item for item in episode_items if item.get("badge") != "预告"]
        episode_items = self._select_items(episode_items)

        return BangumiSeason(
            season_id=season_id,
            title=res["title"],
            items=[
                parse_bangumi_episode(item, require_metadata=self.options.require_metadata)
                for item in episode_items
            ],
        )

    @staticmethod
    async def _get_season_id(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
        media_api = f"https://api.bilibili.com/pgc/review/user?media_id={media_id}"
        res_json = unwrap_fetch_result(await Fetcher.fetch_json(scope, media_api))
        return SeasonId(str(res_json["result"]["media"]["season_id"]))
