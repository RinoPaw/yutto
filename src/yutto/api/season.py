from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from yutto.api.common import fetch_payload
from yutto.types import SeasonId
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import EpisodeId, MediaId


async def get_bangumi_season(scope: ExecutionScope, id: SeasonId | EpisodeId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/pgc/view/web/season?{urlencode(id.to_dict())}",
        "该番剧",
        str(id),
        "result",
    )


get_bangumi_season_by_episode = get_bangumi_season


async def get_season_id_by_media(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
    api = f"https://api.bilibili.com/pgc/review/user?{urlencode(media_id.to_dict())}"
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
    return SeasonId(str(response["result"]["media"]["season_id"]))


async def get_cheese_season(scope: ExecutionScope, id: SeasonId | EpisodeId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/pugv/view/web/season?{urlencode(id.to_dict())}",
        "该课程",
        str(id),
        "data",
    )


get_cheese_season_by_episode = get_cheese_season


__all__ = [
    "get_bangumi_season",
    "get_bangumi_season_by_episode",
    "get_cheese_season",
    "get_cheese_season_by_episode",
    "get_season_id_by_media",
]
