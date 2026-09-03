from __future__ import annotations

import re
from typing import TYPE_CHECKING

from yutto.parser._abc import Parser
from yutto.source.cheese_episode_source import CheeseEpisodeSource
from yutto.source.cheese_season_source import CheeseSeasonSource
from yutto.types import EpisodeId, SeasonId

if TYPE_CHECKING:
    from yutto.source import SourceOptions


class CheeseParser(Parser):
    _CHEESE_EP_URL = re.compile(r"https?://(?:www\.)?bilibili\.com/cheese/play/ep(?P<episode_id>[0-9]+)/?", re.IGNORECASE)
    _CHEESE_SS_URL = re.compile(r"https?://(?:www\.)?bilibili\.com/cheese/play/ss(?P<season_id>[0-9]+)/?", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> CheeseEpisodeSource | CheeseSeasonSource | None:
        if match := self._CHEESE_EP_URL.fullmatch(url):
            return CheeseEpisodeSource(id=EpisodeId(match.group("episode_id")), options=options)

        if match := self._CHEESE_SS_URL.fullmatch(url):
            return CheeseSeasonSource(id=SeasonId(match.group("season_id")), options=options)

        return None
