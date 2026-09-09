from __future__ import annotations

from yutto.parser import parse
from yutto.source import CheeseEpisodeSource, CheeseSeasonSource


def test_cheese_urls_accept_query_and_fragment_suffixes() -> None:
    assert isinstance(
        parse("https://www.bilibili.com/cheese/play/ep1122054?foo=bar"),
        CheeseEpisodeSource,
    )
    assert isinstance(
        parse("https://www.bilibili.com/cheese/play/ss34184/?foo=bar#section"),
        CheeseSeasonSource,
    )
