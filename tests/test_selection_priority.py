from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from returns.result import Success

from yutto.media import BangumiSeason, CheeseSeason
from yutto.parser import ParseOptions, parse
from yutto.source import (
    BangumiEpisodeSource,
    BangumiSeasonSource,
    CheeseEpisodeSource,
    CheeseSeasonSource,
    UgcVideoSource,
)
from yutto.types import EpisodeId


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


def test_episode_and_season_parser_selection_semantics() -> None:
    bangumi_ep = parse("https://www.bilibili.com/bangumi/play/ep102")
    bangumi_ss = parse("https://www.bilibili.com/bangumi/play/ss456")
    cheese_ep = parse("https://www.bilibili.com/cheese/play/ep102")
    cheese_ss = parse("https://www.bilibili.com/cheese/play/ss456")

    assert isinstance(bangumi_ep, BangumiEpisodeSource)
    assert bangumi_ep.selection is None
    assert isinstance(bangumi_ss, BangumiSeasonSource)
    assert bangumi_ss.selection == "1"
    assert isinstance(cheese_ep, CheeseEpisodeSource)
    assert cheese_ep.selection is None
    assert isinstance(cheese_ss, CheeseSeasonSource)
    assert cheese_ss.selection == "1"

    options = ParseOptions(selection="2~-1")
    bangumi_ep = parse("https://www.bilibili.com/bangumi/play/ep102", options)
    bangumi_ss = parse("https://www.bilibili.com/bangumi/play/ss456", options)
    cheese_ep = parse("https://www.bilibili.com/cheese/play/ep102", options)
    cheese_ss = parse("https://www.bilibili.com/cheese/play/ss456", options)

    assert bangumi_ep is not None and bangumi_ep.selection == "2~-1"
    assert bangumi_ss is not None and bangumi_ss.selection == "2~-1"
    assert cheese_ep is not None and cheese_ep.selection == "2~-1"
    assert cheese_ss is not None and cheese_ss.selection == "2~-1"


def test_ugc_selection_priority() -> None:
    source = parse("https://www.bilibili.com/video/BV1D84y1t76J")
    assert isinstance(source, UgcVideoSource)
    assert source.selection == "1"

    source = parse("https://www.bilibili.com/video/BV1D84y1t76J?p=5")
    assert isinstance(source, UgcVideoSource)
    assert source.selection == "5"

    source = parse(
        "https://www.bilibili.com/video/BV1D84y1t76J?p=5",
        ParseOptions(selection="2"),
    )
    assert isinstance(source, UgcVideoSource)
    assert source.selection == "2"

    # 显式 -p 优先时，不需要再解释被覆盖掉的 URL p 参数。
    source = parse(
        "https://www.bilibili.com/video/BV1D84y1t76J?p=not-a-number",
        ParseOptions(selection="3"),
    )
    assert isinstance(source, UgcVideoSource)
    assert source.selection == "3"


def test_bangumi_ep_defaults_to_anchor_but_explicit_selection_targets_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fetcher_stub(monkeypatch, _bangumi_response())

    media = asyncio.run(BangumiEpisodeSource(id=EpisodeId("102")).resolve(cast(Any, None)))
    assert isinstance(media, BangumiSeason)
    assert [item.episode_id for item in media.items] == [EpisodeId("102")]

    media = asyncio.run(
        BangumiEpisodeSource(id=EpisodeId("102"), selection="1~2").resolve(cast(Any, None))
    )
    assert [item.episode_id for item in media.items] == [EpisodeId("101"), EpisodeId("102")]


def test_cheese_ep_defaults_to_anchor_but_explicit_selection_targets_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fetcher_stub(monkeypatch, _cheese_response())

    media = asyncio.run(CheeseEpisodeSource(id=EpisodeId("102")).resolve(cast(Any, None)))
    assert isinstance(media, CheeseSeason)
    assert [item.episode_id for item in media.items] == [EpisodeId("102")]

    media = asyncio.run(
        CheeseEpisodeSource(id=EpisodeId("102"), selection="1~2").resolve(cast(Any, None))
    )
    assert [item.episode_id for item in media.items] == [EpisodeId("101"), EpisodeId("102")]


def test_season_source_defaults_to_first_episode(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(monkeypatch, _bangumi_response())
    source = parse("https://www.bilibili.com/bangumi/play/ss456")
    assert isinstance(source, BangumiSeasonSource)

    media = asyncio.run(source.resolve(cast(Any, None)))
    assert [item.episode_id for item in media.items] == [EpisodeId("101")]
