from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload
from yutto.types import SeasonId
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import EpisodeId, MediaId


async def get_season_by_episode(scope: ExecutionScope, episode_id: EpisodeId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/pgc/view/web/season?ep_id={episode_id}",
        "该番剧",
        f"episode_id: {episode_id}",
        "result",
    )


async def get_season(scope: ExecutionScope, season_id: SeasonId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/pgc/view/web/season?season_id={season_id}",
        "该番剧列表",
        f"season_id: {season_id}",
        "result",
    )


async def get_season_id_by_media(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
    api = f"https://api.bilibili.com/pgc/review/user?media_id={media_id}"
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
    return SeasonId(str(response["result"]["media"]["season_id"]))


__all__ = ["get_season", "get_season_by_episode", "get_season_id_by_media"]
