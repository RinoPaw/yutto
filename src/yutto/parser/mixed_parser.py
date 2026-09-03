from __future__ import annotations

from typing import TYPE_CHECKING

from yutto.parser._abc import Parser
from yutto.source import AmbiguousSource
from yutto.source.bangumi_episode_source import BangumiEpisodeSource
from yutto.source.bangumi_season_source import BangumiSeasonSource
from yutto.source.cheese_episode_source import CheeseEpisodeSource
from yutto.source.cheese_season_source import CheeseSeasonSource
from yutto.types import EpisodeId, SeasonId
from yutto.utils import _EP_ID, _SS_ID

if TYPE_CHECKING:
    from yutto.source import Source, SourceOptions


class MixedParser(Parser):
    def parse(self, url: str, options: SourceOptions) -> Source | None:
        if match := _EP_ID.fullmatch(url):
            episode_id = EpisodeId(match.group("episode_id"))
            return AmbiguousSource(
                id=episode_id,
                options=options,
                candidates=(
                    BangumiEpisodeSource(id=episode_id, options=options),
                    CheeseEpisodeSource(id=episode_id, options=options),
                ),
            )

        if match := _SS_ID.fullmatch(url):
            season_id = SeasonId(match.group("season_id"))
            return AmbiguousSource(
                id=season_id,
                options=options,
                candidates=(
                    BangumiSeasonSource(id=season_id, options=options),
                    CheeseSeasonSource(id=season_id, options=options),
                ),
            )

        return None
