from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload
from yutto.types import SeasonId, format_ids
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import EpisodeId, MediaId


async def get_season(scope: ExecutionScope, id: SeasonId | EpisodeId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/pgc/view/web/season?{id.to_param()}",
        "该番剧",
        format_ids(id),
        "result",
    )


async def get_season_id_by_media(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
    api = f"https://api.bilibili.com/pgc/review/user?{media_id.to_param()}"
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
    return SeasonId(str(response["result"]["media"]["season_id"]))


get_season_by_episode = get_season


__all__ = ["get_season", "get_season_by_episode", "get_season_id_by_media"]
