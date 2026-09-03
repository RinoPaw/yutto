from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from yutto.exceptions import (
    WrongArgumentError,
)
from yutto.parser._abc import Parser
from yutto.parser.parser import _BILIBILI, _URL_END
from yutto.source import UgcVideoSource
from yutto.types import AId, BvId
from yutto.utils import _AV_ID, _BV_ID

if TYPE_CHECKING:
    from yutto.source import Source, SourceOptions
    from yutto.types import AvId


class UgcVideoParser(Parser):
    _UGC_AV_URL = re.compile(rf"{_BILIBILI}/video/av(?P<aid>[0-9]+){_URL_END}", re.IGNORECASE)
    _UGC_BV_URL = re.compile(rf"{_BILIBILI}/video/(?P<bvid>BV[A-Za-z0-9]+){_URL_END}", re.IGNORECASE)
    _FESTIVAL_URL = re.compile(rf"{_BILIBILI}/festival/", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        query = parse_qs(urlparse(url).query, keep_blank_values=True)

        avid = self._parse_avid(url, query)
        if avid is None:
            return None
        page = self._parse_page(query)

        return UgcVideoSource(id=avid, page=page, options=options)

    def _parse_avid(self, url: str, query: dict[str, list[str]]) -> AvId | None:
        if match := self._UGC_AV_URL.fullmatch(url):
            return AId(match.group("aid"))

        if match := self._UGC_BV_URL.fullmatch(url):
            return BvId(match.group("bvid"))

        if self._FESTIVAL_URL.match(url):
            return self._parse_avid_from_query(query)

        if match := _AV_ID.match(url):
            return AId(match.group("aid"))

        if match := _BV_ID.match(url):
            return BvId(match.group("bvid"))

        return None

    def _parse_page(self, query: dict[str, list[str]]) -> int:
        page = self._single_query_value(query, "p")
        if page is None:
            return 1
        try:
            return int(page)
        except ValueError:
            raise WrongArgumentError(f"page `{page}` 不是整数") from None

    def _parse_avid_from_query(self, query: dict[str, list[str]]) -> AvId | None:
        bvid = self._single_query_value(query, "bvid")
        aid = self._single_query_value(query, "aid")
        oid = self._single_query_value(query, "oid")

        values = [
            BvId(bvid) if bvid else None,
            AId(aid) if aid else None,
            AId(oid) if oid else None,
        ]
        values = [v for v in values if v]
        return values[0]
