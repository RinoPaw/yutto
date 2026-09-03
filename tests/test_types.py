from __future__ import annotations

import pytest

from yutto.types import (
    AId,
    BilibiliId,
    BvId,
    CId,
    CollectionId,
    EpisodeId,
    FId,
    MId,
    MediaId,
    SeasonId,
    SeriesId,
)


def test_bilibili_id_equality() -> None:
    assert AId("123") == AId("123")
    assert AId("123") != AId("456")

    assert AId("123") != CId("123")
    assert EpisodeId("123") != SeasonId("123")


@pytest.mark.parametrize(
    "id_type",
    (AId, CId, EpisodeId, MediaId, SeasonId, MId, FId, SeriesId, CollectionId),
)
def test_numeric_id_validation(id_type: type[BilibiliId]) -> None:
    assert id_type("123").value == "123"

    for value in ("", "abc", "１２３"):
        with pytest.raises(ValueError):
            id_type(value)


def test_bvid_validation() -> None:
    assert BvId("BV1f34y1k7D5").value == "BV1f34y1k7D5"

    for value in ("", "123", "BV", "BV测试"):
        with pytest.raises(ValueError):
            BvId(value)


def test_generic_bilibili_id_accepts_non_numeric_value() -> None:
    assert BilibiliId("watchlater").value == "watchlater"
