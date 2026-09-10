from __future__ import annotations

from typing import TYPE_CHECKING, Any

from yutto.api.common import fetch_payload
from yutto.types import format_ids

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import EpisodeId, SeasonId


async def get_season(scope: ExecutionScope, id: SeasonId | EpisodeId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/pugv/view/web/season?{id.to_param()}",
        "该课程",
        format_ids(id),
        "data",
    )


get_season_by_episode = get_season


__all__ = ["get_season", "get_season_by_episode"]
