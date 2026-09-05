from __future__ import annotations

import pytest

from yutto.exceptions import WrongArgumentError
from yutto.parser import ParseOptions, parse
from yutto.selection import compile_selection
from yutto.source import UgcSeriesSource, UgcVideoSource


def test_compile_selection() -> None:
    assert compile_selection("1", 4) == (1,)
    assert compile_selection("1~-1", 4) == (1, 2, 3, 4)
    assert compile_selection("~", 4) == (1, 2, 3, 4)
    assert compile_selection("-2~-1", 4) == (3, 4)
    assert compile_selection("^,$", 4) == (1, 4)
    assert compile_selection("3,1,3", 4) == (1, 3)


@pytest.mark.parametrize("selection", ["", "0", "5", "3~2", "1~~2", "foo"])
def test_compile_selection_rejects_invalid_expressions(selection: str) -> None:
    with pytest.raises(WrongArgumentError):
        compile_selection(selection, 4)


def test_parser_sets_context_selection() -> None:
    video = parse("BV1D84y1t76J")
    assert isinstance(video, UgcVideoSource)
    assert video.selection == "1"

    video = parse("https://www.bilibili.com/video/BV1D84y1t76J?p=2")
    assert isinstance(video, UgcVideoSource)
    assert video.selection == "2"

    video = parse(
        "https://www.bilibili.com/video/BV1D84y1t76J?p=2",
        ParseOptions(selection="3"),
    )
    assert isinstance(video, UgcVideoSource)
    assert video.selection == "3"

    series = parse(
        "https://space.bilibili.com/123/lists/456?type=series",
        ParseOptions(selection="3"),
    )
    assert isinstance(series, UgcSeriesSource)
    assert series.selection == "3"
