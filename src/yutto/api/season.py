from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from yutto.api.common import fetch_payload
from yutto.exceptions import NotFoundError
from yutto.types import SeasonId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import EpisodeId, MediaId


async def get_bangumi_season(scope: ExecutionScope, id: SeasonId | EpisodeId) -> dict[str, Any]:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/pgc/view/web/season?{urlencode(id.to_dict())}",
        "该番剧",
        str(id),
        "result",
    )
    if not isinstance(payload.get("episodes"), list):
        raise NotFoundError(f"无法解析该番剧（{id}），原因：API 响应缺少剧集列表")
    return payload


get_bangumi_season_by_episode = get_bangumi_season


async def get_season_id_by_media(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/pgc/review/user?{urlencode(media_id.to_dict())}",
        "该番剧",
        str(media_id),
        "result",
    )
    media = payload.get("media")
    season_id = media.get("season_id") if isinstance(media, dict) else None
    if season_id is None:
        raise NotFoundError(f"无法解析该番剧（{media_id}），原因：API 响应缺少 season_id")
    return SeasonId(str(season_id))


async def get_cheese_season(scope: ExecutionScope, id: SeasonId | EpisodeId) -> dict[str, Any]:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/pugv/view/web/season?{urlencode(id.to_dict())}",
        "该课程",
        str(id),
        "data",
    )
    if not isinstance(payload.get("episodes"), list):
        raise NotFoundError(f"无法解析该课程（{id}），原因：API 响应缺少剧集列表")
    return payload


get_cheese_season_by_episode = get_cheese_season


__all__ = [
    "get_bangumi_season",
    "get_bangumi_season_by_episode",
    "get_cheese_season",
    "get_cheese_season_by_episode",
    "get_season_id_by_media",
]
