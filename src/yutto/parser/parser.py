from __future__ import annotations

from typing import TYPE_CHECKING

from yutto.source import SourceOptions

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.source import Source

_BILIBILI = r"https?://(?:www\.)?bilibili\.com"
_SPACE_BILIBILI = r"https?://space\.bilibili\.com"
_URL_END = r"(?:/(?:[?#].*)?|(?:[?#].*)?)"


async def parse_source(
    scope: ExecutionScope,
    value: str,
    options: SourceOptions | None = None,
) -> Source | None:
    del scope
    value = value.strip()
    if not value:
        return None
    options = options or SourceOptions()

    from yutto.parser.bangumi_parser import BangumiParser
    from yutto.parser.cheese_parser import CheeseParser
    from yutto.parser.mixed_parser import MixedParser
    from yutto.parser.ugc_collection_parser import UgcCollectionParser
    from yutto.parser.ugc_list_parser import UgcListParser
    from yutto.parser.ugc_series_parser import UgcSeriesParser
    from yutto.parser.ugc_video_parser import UgcVideoParser

    for parser in (
        BangumiParser(),
        CheeseParser(),
        UgcSeriesParser(),
        UgcCollectionParser(),
        UgcListParser(),
        MixedParser(),
        UgcVideoParser(),
    ):
        source = parser.parse(value, options)
        if source is not None:
            return source
    return None
