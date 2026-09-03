from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from yutto.parser._abc import Parser
from yutto.parser.parser import _SPACE_BILIBILI, _URL_END
from yutto.source import UgcFavSource
from yutto.types import FId

if TYPE_CHECKING:
    from yutto.source import Source, SourceOptions


class UgcFavParser(Parser):
    _FAVOURITE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)
        if not self._FAVOURITE_URL.fullmatch(url):
            return None
        if self._single_query_value(query, "ftype") == "collect":
            return None
        fid = self._single_query_value(query, "fid")
        if fid is None:
            return None
        return UgcFavSource(id=FId(fid), options=options)
