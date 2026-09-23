from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.exceptions import NoAccessPermissionError, NotFoundError, WrongArgumentError
from yutto.media import BangumiEpisode, BangumiSeason, CheeseEpisode, CheeseSeason, UgcVideo
from yutto.parser import parse
from yutto.scope import ROOT_SCOPE, Scope
from yutto.source import (
    AmbiguousEpisodeSource,
    AmbiguousSeasonSource,
    BangumiEpisodeSource,
    BangumiSeasonSource,
    CheeseEpisodeSource,
    CheeseSeasonSource,
    UgcCollectionSource,
    UgcFavSource,
    UgcSeriesSource,
    UgcSpaceSource,
    UgcVideoSource,
    UgcWatchLaterSource,
)
from yutto.types import EpisodeId, MediaId, SeasonId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

_NOT_FOUND = {"code": -404, "message": "啥都木有"}
_DEFAULT_SCOPE = Scope(parent=ROOT_SCOPE)
_EXECUTION = cast("ExecutionScope", None)


def _scope(values: dict[str, object]) -> Scope:
    return Scope(values, parent=ROOT_SCOPE)


def _parse(value: str) -> Any:
    return parse(value)


def _episode_source(episode_id: EpisodeId) -> AmbiguousEpisodeSource:
    return AmbiguousEpisodeSource(id=episode_id)


def _season_source(season_id: SeasonId) -> AmbiguousSeasonSource:
    return AmbiguousSeasonSource(id=season_id)


def _bangumi_season_response(*episode_ids: str) -> dict[str, Any]:
    return {
        "code": 0,
        "result": {
            "season_id": 456,
            "media_id": 789,
            "title": "番剧",
            "episodes": [
                {
                    "id": int(episode_id),
                    "title": str(i + 1),
                    "long_title": f"第{i + 1}话",
                    "cid": 100 + i,
                    "bvid": "BV1D84y1t76J",
                    "badge": "",
                    "share_copy": f"番剧 第{i + 1}话",
                    "cover": f"https://img/{i}.jpg",
                    "pub_time": 1700000000 + i,
                }
                for i, episode_id in enumerate(episode_ids)
            ],
        },
    }


def _cheese_season_response(*episode_ids: str) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "title": "课程",
            "episodes": [
                {
                    "id": int(episode_id),
                    "title": f"第{i + 1}节",
                    "cid": 200 + i,
                    "aid": 300 + i,
                    "cover": f"https://img/{i}.jpg",
                    "release_date": 1700000000 + i,
                }
                for i, episode_id in enumerate(episode_ids)
            ],
        },
    }


def _install_fetcher_stub(monkeypatch: pytest.MonkeyPatch, routes: dict[str, Any]) -> list[str]:
    calls: list[str] = []

    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        calls.append(url)
        for fragment, response in routes.items():
            if fragment in url:
                if isinstance(response, BaseException):
                    raise response
                return Success(response)
        raise AssertionError(f"unexpected fetch url: {url}")

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    return calls


def test_parse_namespace_urls() -> None:
    assert isinstance(_parse("https://www.bilibili.com/bangumi/play/ep123"), BangumiEpisodeSource)
    assert isinstance(_parse("https://www.bilibili.com/bangumi/play/ss456"), BangumiSeasonSource)
    assert isinstance(_parse("https://www.bilibili.com/bangumi/media/md789"), BangumiSeasonSource)
    assert isinstance(_parse("https://www.bilibili.com/cheese/play/ep1122054"), CheeseEpisodeSource)
    assert isinstance(_parse("https://www.bilibili.com/cheese/play/ss34184"), CheeseSeasonSource)
    assert isinstance(_parse("https://www.bilibili.com/video/BV1D84y1t76J?p=5"), UgcVideoSource)
    assert isinstance(_parse("av123"), UgcVideoSource)
    source = _parse("BV1D84y1t76J?p=2")
    assert isinstance(source, UgcVideoSource)
    assert source.page == 2
    assert _parse("https://example.com/video/BV1D84y1t76J") is None


def test_parse_ugc_container_urls() -> None:
    assert isinstance(_parse("https://space.bilibili.com/123/favlist?fid=456"), UgcFavSource)
    assert isinstance(_parse("https://space.bilibili.com/123/favlist?fid=456&ftype=collect"), UgcCollectionSource)
    assert isinstance(_parse("https://space.bilibili.com/123/lists/456?type=series"), UgcSeriesSource)
    assert isinstance(_parse("https://space.bilibili.com/123/video"), UgcSpaceSource)
    assert isinstance(_parse("https://www.bilibili.com/list/watchlater"), UgcWatchLaterSource)


def test_parse_bare_ids_route_to_specialized_ambiguous_sources() -> None:
    source = _parse("ep779775")
    assert isinstance(source, AmbiguousEpisodeSource)
    assert source.id == EpisodeId("779775")
    source = _parse("ss34184")
    assert isinstance(source, AmbiguousSeasonSource)
    assert source.id == SeasonId("34184")
    assert isinstance(_parse("md789"), BangumiSeasonSource)


def test_bangumi_episode_source_single_request_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fetcher_stub(monkeypatch, {"pgc/view/web/season": _bangumi_season_response("123")})
    result = asyncio.run(BangumiEpisodeSource(id=EpisodeId("123")).resolve(_EXECUTION, _DEFAULT_SCOPE))
    assert isinstance(result.media, BangumiEpisode)
    assert result.media.episode_id == EpisodeId("123")
    assert result.media.metadata.title == "1 第1话"
    assert len(calls) == 1


def test_cheese_episode_source_rejects_quirk_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(monkeypatch, {"pugv/view/web/season": _cheese_season_response("999")})
    with pytest.raises(NotFoundError):
        asyncio.run(CheeseEpisodeSource(id=EpisodeId("779775")).resolve(_EXECUTION, _DEFAULT_SCOPE))


def test_episode_source_resolves_each_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {"pgc/view/web/season": _bangumi_season_response("779775"), "pugv/view/web/season": _NOT_FOUND},
    )
    result = asyncio.run(_episode_source(EpisodeId("779775")).resolve(_EXECUTION, _DEFAULT_SCOPE))
    assert isinstance(result.media, BangumiEpisode)

    _install_fetcher_stub(
        monkeypatch,
        {"pgc/view/web/season": _NOT_FOUND, "pugv/view/web/season": _cheese_season_response("779775")},
    )
    result = asyncio.run(_episode_source(EpisodeId("779775")).resolve(_EXECUTION, _DEFAULT_SCOPE))
    assert isinstance(result.media, CheeseEpisode)


def test_episode_source_raises_for_ambiguous_or_missing_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _bangumi_season_response("779775"),
            "pugv/view/web/season": _cheese_season_response("779775"),
        },
    )
    with pytest.raises(WrongArgumentError):
        asyncio.run(_episode_source(EpisodeId("779775")).resolve(_EXECUTION, _DEFAULT_SCOPE))

    _install_fetcher_stub(monkeypatch, {"pgc/view/web/season": _NOT_FOUND, "pugv/view/web/season": _NOT_FOUND})
    with pytest.raises(NotFoundError):
        asyncio.run(_episode_source(EpisodeId("999999")).resolve(_EXECUTION, _DEFAULT_SCOPE))


def test_episode_source_propagates_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {"pgc/view/web/season": {"code": -403, "message": "请求被拦截"}, "pugv/view/web/season": _NOT_FOUND},
    )
    with pytest.raises(NoAccessPermissionError):
        asyncio.run(_episode_source(EpisodeId("123")).resolve(_EXECUTION, _DEFAULT_SCOPE))


def test_season_source_resolves_media_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/review/user": {"code": 0, "result": {"media": {"season_id": 456}}},
            "pgc/view/web/season": _bangumi_season_response("123"),
        },
    )
    result = asyncio.run(BangumiSeasonSource(id=MediaId("789")).resolve(_EXECUTION, _DEFAULT_SCOPE))
    assert isinstance(result.media, BangumiSeason)
    assert result.media.season_id == SeasonId("456")


def test_bangumi_filters_extra_preview_and_then_selects(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _bangumi_season_response("123", "124")
    response["result"]["episodes"][0]["badge"] = "预告"
    response["result"]["section"] = [
        {
            "type": 1,
            "episodes": [
                {
                    "id": 125,
                    "title": "特别篇",
                    "long_title": "",
                    "cid": 125,
                    "bvid": "BV1D84y1t76J",
                    "badge": "",
                    "share_copy": "番剧 特别篇",
                    "cover": "https://img/125.jpg",
                    "pub_time": 1700000125,
                }
            ],
        }
    ]
    _install_fetcher_stub(monkeypatch, {"pgc/view/web/season": response})
    scope = _scope(
        {
            "selection.expression": "1~-1",
            "selection.with_extra_episodes": True,
            "selection.skip_preview": True,
        }
    )
    result = asyncio.run(BangumiSeasonSource(id=SeasonId("456")).resolve(_EXECUTION, scope))
    assert isinstance(result.media, BangumiSeason)
    assert [item.episode_id for item in result.media.items] == [EpisodeId("124"), EpisodeId("125")]


def test_ugc_selection_overrides_url_page_at_resolve_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "/x/web-interface/view": {
                "code": 0,
                "data": {
                    "aid": 808982399,
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
        },
    )
    source = parse("https://www.bilibili.com/video/BV1D84y1t76J?p=2")
    assert isinstance(source, UgcVideoSource)
    result = asyncio.run(source.resolve(_EXECUTION, _DEFAULT_SCOPE))
    assert isinstance(result.media, UgcVideo)
    assert [page.index for page in result.media.items] == [2]

    result = asyncio.run(source.resolve(_EXECUTION, _scope({"selection.expression": "3,5,1,3"})))
    assert isinstance(result.media, UgcVideo)
    assert [page.index for page in result.media.items] == [3, 1]


@pytest.mark.parametrize(
    ("source", "response_key", "expected_type"),
    [
        (BangumiEpisodeSource(id=EpisodeId("102")), "pgc/view/web/season", BangumiSeason),
        (CheeseEpisodeSource(id=EpisodeId("102")), "pugv/view/web/season", CheeseSeason),
    ],
)
def test_episode_selection_targets_whole_season(
    monkeypatch: pytest.MonkeyPatch,
    source: BangumiEpisodeSource | CheeseEpisodeSource,
    response_key: str,
    expected_type: type[BangumiSeason] | type[CheeseSeason],
) -> None:
    response = (
        _bangumi_season_response("101", "102", "103")
        if isinstance(source, BangumiEpisodeSource)
        else _cheese_season_response("101", "102", "103")
    )
    _install_fetcher_stub(monkeypatch, {response_key: response})
    result = asyncio.run(source.resolve(_EXECUTION, _scope({"selection.expression": "3,1,3"})))
    assert isinstance(result.media, expected_type)
    assert [item.episode_id for item in result.media.items] == [EpisodeId("103"), EpisodeId("101")]


def test_seasons_default_to_all_episodes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(monkeypatch, {"pgc/view/web/season": _bangumi_season_response("101", "102", "103")})
    result = asyncio.run(BangumiSeasonSource(id=SeasonId("456")).resolve(_EXECUTION, _DEFAULT_SCOPE))
    assert isinstance(result.media, BangumiSeason)
    assert [item.index for item in result.media.items] == [1, 2, 3]

    _install_fetcher_stub(monkeypatch, {"pugv/view/web/season": _cheese_season_response("101", "102", "103")})
    result = asyncio.run(CheeseSeasonSource(id=SeasonId("456")).resolve(_EXECUTION, _DEFAULT_SCOPE))
    assert isinstance(result.media, CheeseSeason)
    assert [item.index for item in result.media.items] == [1, 2, 3]
