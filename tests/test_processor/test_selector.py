from __future__ import annotations

import pytest

from yutto.exceptions import WrongArgumentError
from yutto.selection import compile_selection, parse_selection

pytestmark = pytest.mark.processor


@pytest.mark.parametrize(
    "selection",
    [
        "1",
        "99",
        "-1",
        "$",
        "1,2",
        "1,-2,3,-4",
        "1~3",
        "1~-1",
        "-2~-1",
        "1~2,9~$",
        "~2,9~",
        "~",
    ],
)
def test_selection_accepts_supported_syntax(selection: str) -> None:
    parse_selection(selection)


@pytest.mark.parametrize(
    "selection",
    ["", " ", "x", "- 1", "1$", "1,", "1~2~3", "1,,2", "01"],
)
def test_selection_rejects_invalid_syntax(selection: str) -> None:
    with pytest.raises(WrongArgumentError):
        parse_selection(selection)


def test_selection_resolves_single_and_negative_positions() -> None:
    assert compile_selection("1", 24) == (1,)
    assert compile_selection("11", 24) == (11,)
    assert compile_selection("-1", 24) == (24,)
    assert compile_selection("-10", 24) == (15,)
    assert compile_selection("$", 24) == (24,)


def test_selection_resolves_composition_and_deduplicates() -> None:
    assert compile_selection("1,2,4", 24) == (1, 2, 4)
    assert compile_selection("11,-1,$", 24) == (11, 24)
    assert compile_selection("3,1,3,1~2", 4) == (3, 1, 2)


def test_selection_resolves_ranges_and_preserves_direction() -> None:
    assert compile_selection("1~4", 24) == (1, 2, 3, 4)
    assert compile_selection("2~-2", 6) == (2, 3, 4, 5)
    assert compile_selection("2~$", 6) == (2, 3, 4, 5, 6)
    assert compile_selection("3~1", 4) == (3, 2, 1)


def test_selection_resolves_open_ranges() -> None:
    assert compile_selection("~4,20~", 24) == (1, 2, 3, 4, 20, 21, 22, 23, 24)
    assert compile_selection("~", 24) == tuple(range(1, 25))


def test_selection_allows_whitespace_between_tokens() -> None:
    assert compile_selection("  3 , 1 ~ -1 , ^  ", 4) == (3, 1, 2, 4)


@pytest.mark.parametrize("selection", ["0", "25", "-25"])
def test_selection_rejects_out_of_range_positions(selection: str) -> None:
    with pytest.raises(WrongArgumentError):
        compile_selection(selection, 24)
