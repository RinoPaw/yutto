from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import EpisodeId, SeasonId


async def get_season_by_episode(scope: ExecutionScope, episode_id: EpisodeId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/pugv/view/web/season?ep_id={episode_id}",
        "该课程",
        f"episode_id: {episode_id}",
        "data",
    )


async def get_season(scope: ExecutionScope, season_id: SeasonId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/pugv/view/web/season?season_id={season_id}",
        "该课程列表",
        f"season_id: {season_id}",
        "data",
    )


__all__ = ["get_season", "get_season_by_episode"]
