from __future__ import annotations

import pytest

from yutto.exceptions import WrongArgumentError
from yutto.parser import parse
from yutto.selection import Anchor, Index, Range, compile_selection, parse_selection
from yutto.source import UgcSeriesSource, UgcVideoSource


def test_parse_selection_builds_ast() -> None:
    selection = parse_selection("1, -2~$, ^, ~3, 4~")

    assert selection.items == (
        Index(1),
        Range(Index(-2), Anchor.LAST),
        Anchor.FIRST,
        Range(None, Index(3)),
        Range(Index(4), None),
    )


def test_compile_selection_preserves_order_and_duplicates() -> None:
    assert compile_selection("3,1,3,1~2", 4) == (3, 1, 3, 1, 2)
    assert compile_selection("^,$,-1,~2,3~", 4) == (1, 4, 4, 1, 2, 3, 4)


def test_compile_selection_preserves_range_direction() -> None:
    assert compile_selection("1~3", 4) == (1, 2, 3)
    assert compile_selection("3~1", 4) == (3, 2, 1)
    assert compile_selection("-1~-2", 4) == (4, 3)
    assert compile_selection("-2~-1", 4) == (3, 4)


def test_compile_selection_resolves_open_ranges_and_anchors() -> None:
    assert compile_selection("1~-1", 4) == (1, 2, 3, 4)
    assert compile_selection("~", 4) == (1, 2, 3, 4)
    assert compile_selection("^~$", 4) == (1, 2, 3, 4)


def test_selection_allows_whitespace_between_tokens() -> None:
    assert compile_selection("  3 , 1 ~ -1 , ^  ", 4) == (3, 1, 2, 3, 4, 1)


@pytest.mark.parametrize(
    "selection",
    ["", "   ", "1,,2", "1,", ",1", "1~~2", "foo", "01", "-", "1 2", "- 1", "1+2"],
)
def test_parse_selection_rejects_invalid_syntax(selection: str) -> None:
    with pytest.raises(WrongArgumentError):
        parse_selection(selection)


@pytest.mark.parametrize("selection", ["0", "5", "-5"])
def test_compile_selection_rejects_invalid_semantics(selection: str) -> None:
    with pytest.raises(WrongArgumentError):
        compile_selection(selection, 4)


def test_compile_selection_validates_syntax_before_context_size() -> None:
    with pytest.raises(WrongArgumentError, match="无法识别字符"):
        compile_selection("foo", 0)

    with pytest.raises(WrongArgumentError, match="没有可供选择"):
        compile_selection("1", 0)


def test_parser_only_records_input_facts() -> None:
    video = parse("BV1D84y1t76J")
    assert isinstance(video, UgcVideoSource)
    assert video.page is None
    assert not hasattr(video, "options")

    video = parse("https://www.bilibili.com/video/BV1D84y1t76J?p=2")
    assert isinstance(video, UgcVideoSource)
    assert video.page == 2

    series = parse("https://space.bilibili.com/123/lists/456?type=series")
    assert isinstance(series, UgcSeriesSource)
    assert not hasattr(series, "options")


@pytest.mark.parametrize("page", ["0", "-1"])
def test_parser_rejects_non_positive_url_page(page: str) -> None:
    with pytest.raises(WrongArgumentError, match="正整数"):
        parse(f"https://www.bilibili.com/video/BV1D84y1t76J?p={page}")
