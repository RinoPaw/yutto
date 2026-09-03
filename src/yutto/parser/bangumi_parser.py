from __future__ import annotations

import re
from typing import TYPE_CHECKING

from yutto.parser._abc import Parser
from yutto.parser.parser import _BILIBILI, _URL_END
from yutto.source import BangumiEpisodeSource, BangumiSeasonSource
from yutto.types import EpisodeId, MediaId, SeasonId
from yutto.utils import _MD_ID

if TYPE_CHECKING:
    from yutto.source import SourceOptions


class BangumiParser(Parser):
    _BANGUMI_EP_URL = re.compile(rf"{_BILIBILI}/bangumi/play/ep(?P<episode_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _BANGUMI_SS_URL = re.compile(rf"{_BILIBILI}/bangumi/play/ss(?P<season_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _BANGUMI_MD_URL = re.compile(rf"{_BILIBILI}/bangumi/media/md(?P<media_id>[0-9]+){_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> BangumiEpisodeSource | BangumiSeasonSource | None:
        if match := self._BANGUMI_SS_URL.fullmatch(url):
            return BangumiSeasonSource(id=SeasonId(match.group("season_id")), options=options)

        if match := self._BANGUMI_EP_URL.fullmatch(url):
            return BangumiEpisodeSource(id=EpisodeId(match.group("episode_id")), options=options)

        if match := self._BANGUMI_MD_URL.fullmatch(url):
            return BangumiSeasonSource(id=MediaId(match.group("media_id")), options=options)

        if match := _MD_ID.fullmatch(url):
            return BangumiSeasonSource(id=MediaId(match.group("media_id")), options=options)

        return None
