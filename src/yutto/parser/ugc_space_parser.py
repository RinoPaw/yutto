from __future__ import annotations

import re

from yutto.parser._abc import Parser
from yutto.parser.parser import _SPACE_BILIBILI, _URL_END
from yutto.source import UgcSpaceSource
from yutto.types import MId

if TYPE_CHECKING:
    from yutto.source import Source, SourceOptions


class UgcSpaceParser(Parser):
    _SPACE_URL = re.compile(rf"{_SPACE_BILIBILI}/(?P<mid>[0-9]+){_URL_END}", re.IGNORECASE)

    def parse(self, url: str, options: SourceOptions) -> Source | None:
        if match := self._SPACE_URL.fullmatch(url):
            return UgcSpaceSource(id=MId(match.group("mid")), options=options)
        return None
