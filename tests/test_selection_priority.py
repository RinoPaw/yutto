from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, cast

import pytest
from returns.result import Success

from yutto.core.options import SourceOptions
from yutto.exceptions import WrongArgumentError
from yutto.media import BangumiSeason, CheeseSeason
from yutto.parser import parse
from yutto.selection import parse_selection
from yutto.source import (
    BangumiEpisodeSource,
    BangumiSeasonSource,
    CheeseEpisodeSource,
    CheeseSeasonSource,
    UgcVideoSource,
)
from yutto.types import EpisodeId

_DEFAULT_OPTIONS = SourceOptions(
    selection=None,
    with_extra_episodes=False,
    skip_preview=False,
    require_metadata=False,
)


def _install_fetcher_stub(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]) -> None:
    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        return Success(response)

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)


def _bangumi_response() -> dict[str, Any]:
    return {
        "code": 0,
        "result": {
            "season_id": 456,
            "title": "番剧",
            "episodes": [
                {
                    "id": episode_id,
                    "title": str(index),
                    "long_title": f"第{index}话",
                    "cid": 100 + index,
                    "bvid": f"BV{episode_id}",
                    "badge": "",
                    "share_copy": f"番剧 第{index}话",
                    "cover": f"https://img/{index}.jpg",
                    "pub_time": 1700000000 + index,
                }
                for index, episode_id in enumerate((101, 102, 103), start=1)
            ],
        },
    }


def _cheese_response() -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "season_id": 456,
            "title": "课程",
            "episodes": [
                {
                    "id": episode_id,
                    "title": f"第{index}节",
                    "cid": 200 + index,
                    "aid": 300 + index,
                    "cover": f"https://img/{index}.jpg",
                    "release_date": 1700000000 + index,
                }
                for index, episode_id in enumerate((101, 102, 103), start=1)
            ],
        },
    }


def _ugc_response() -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "bvid": "BV1D84y1t76J",
            "title": "投稿",
            "desc": "简介",
            "pic": "https://img/cover.jpg",
            "pubdate": 1700000000,
            "pages": [
                {"cid": 101, "part": "P1"},
                {"cid": 102, "part": "P2"},
                {"cid": 103, "part": "P3"},
            ],
        },
    }


def test_parser_does_not_receive_source_options() -> None:
    for value, source_type in (
        ("https://www.bilibili.com/bangumi/play/ep102", BangumiEpisodeSource),
        ("https://www.bilibili.com/bangumi/play/ss456", BangumiSeasonSource),
        ("https://www.bilibili.com/cheese/play/ep102", CheeseEpisodeSource),
        ("https://www.bilibili.com/cheese/play/ss456", CheeseSeasonSource),
    ):
        source = parse(value)
        assert isinstance(source, source_type)
        assert not hasattr(source, "options")


def test_ugc_url_page_is_an_input_fact() -> None:
    source = parse("https://www.bilibili.com/video/BV1D84y1t76J")
    assert isinstance(source, UgcVideoSource)
    assert source.page is None

    source = parse("https://www.bilibili.com/video/BV1D84y1t76J?p=5")
    assert isinstance(source, UgcVideoSource)
    assert source.page == 5

    with pytest.raises(WrongArgumentError, match="不是整数"):
        parse("https://www.bilibili.com/video/BV1D84y1t76J?p=not-a-number")


def test_ugc_selection_overrides_url_page_at_resolve_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(monkeypatch, _ugc_response())
    source = parse("https://www.bilibili.com/video/BV1D84y1t76J?p=2")
    assert isinstance(source, UgcVideoSource)

    media = asyncio.run(source.resolve(cast(Any, None), _DEFAULT_OPTIONS))
    assert [page.title for page in media.items] == ["P2"]

    media = asyncio.run(
        source.resolve(
            cast(Any, None),
            replace(_DEFAULT_OPTIONS, selection=parse_selection("3")),
        )
    )
    assert [page.title for page in media.items] == ["P3"]


def test_bangumi_ep_defaults_to_anchor_but_explicit_selection_targets_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fetcher_stub(monkeypatch, _bangumi_response())
    source = BangumiEpisodeSource(id=EpisodeId("102"))

    media = asyncio.run(source.resolve(cast(Any, None), _DEFAULT_OPTIONS))
    assert isinstance(media, BangumiSeason)
    assert [item.episode_id for item in media.items] == [EpisodeId("102")]

    media = asyncio.run(
        source.resolve(
            cast(Any, None),
            replace(_DEFAULT_OPTIONS, selection=parse_selection("1~2")),
        )
    )
    assert [item.episode_id for item in media.items] == [EpisodeId("101"), EpisodeId("102")]


def test_cheese_ep_defaults_to_anchor_but_explicit_selection_targets_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fetcher_stub(monkeypatch, _cheese_response())
    source = CheeseEpisodeSource(id=EpisodeId("102"))

    media = asyncio.run(source.resolve(cast(Any, None), _DEFAULT_OPTIONS))
    assert isinstance(media, CheeseSeason)
    assert [item.episode_id for item in media.items] == [EpisodeId("102")]

    media = asyncio.run(
        source.resolve(
            cast(Any, None),
            replace(_DEFAULT_OPTIONS, selection=parse_selection("1~2")),
        )
    )
    assert [item.episode_id for item in media.items] == [EpisodeId("101"), EpisodeId("102")]


def test_season_source_defaults_to_first_episode(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(monkeypatch, _bangumi_response())
    source = parse("https://www.bilibili.com/bangumi/play/ss456")
    assert isinstance(source, BangumiSeasonSource)

    media = asyncio.run(source.resolve(cast(Any, None), _DEFAULT_OPTIONS))
    assert [item.episode_id for item in media.items] == [EpisodeId("101")]
