from __future__ import annotations

import re
from typing import TYPE_CHECKING

from yutto.parser._abc import Parser
from yutto.parser.parser import _BILIBILI, _URL_END
from yutto.source import UgcWatchLaterSource
from yutto.types import BilibiliId

if TYPE_CHECKING:
    from yutto.source import Source, SourceOptions


class UgcWatchLaterParser(Parser):
    _WATCH_LATER_URL = re.compile(rf"{_BILIBILI}/(?:list/)?watchlater{_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        if self._WATCH_LATER_URL.fullmatch(url):
            return UgcWatchLaterSource(id=BilibiliId("watchlater"), options=options)
        return None
