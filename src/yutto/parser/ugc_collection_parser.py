from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from yutto.parser._abc import Parser
from yutto.parser.parser import _SPACE_BILIBILI, _URL_END
from yutto.source import UgcCollectionSource
from yutto.types import CollectionId, MId

if TYPE_CHECKING:
    from yutto.source import Source, SourceOptions


class UgcCollectionParser(Parser):
    _SPACE_LIST_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/lists/(?P<list_id>[0-9]+){_URL_END}", re.IGNORECASE)
    _FAVOURITE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+)/favlist{_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)

        if match := self._SPACE_LIST_URL.fullmatch(url):
            if self._single_query_value(query, "type") != "season":
                return None
            return UgcCollectionSource(
                id=CollectionId(match.group("list_id")),
                owner_id=MId(match.group("mid")),
                options=options,
            )

        if match := self._FAVOURITE_URL.fullmatch(url):
            if self._single_query_value(query, "ftype") != "collect":
                return None
            fid = self._single_query_value(query, "fid")
            if fid is None:
                return None
            return UgcCollectionSource(
                id=CollectionId(fid),
                owner_id=MId(match.group("mid")),
                options=options,
            )

        return None
