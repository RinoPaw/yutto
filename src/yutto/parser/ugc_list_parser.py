from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from yutto.parser._abc import Parser
from yutto.parser.parser import _BILIBILI, _SPACE_BILIBILI, _URL_END
from yutto.source import UgcListSource
from yutto.types import BilibiliId, FId

if TYPE_CHECKING:
    from yutto.source import Source, SourceOptions


class UgcListParser(Parser):
    _WATCH_LATER_URL = re.compile(rf"{_BILIBILI}/(?:list/)?watchlater{_URL_END}", re.IGNORECASE)
    _FAVOURITE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)

        if self._WATCH_LATER_URL.fullmatch(url):
            return UgcListSource(id=BilibiliId("watchlater"), kind="watch_later", options=options)

        if self._FAVOURITE_URL.fullmatch(url):
            if self._single_query_value(query, "ftype") == "collect":
                return None
            fid = self._single_query_value(query, "fid")
            if fid is None:
                return None
            return UgcListSource(id=FId(fid), kind="favourite", options=options)

        return None
