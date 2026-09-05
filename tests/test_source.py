from __future__ import annotations

import asyncio
from typing import Any

import pytest
from returns.result import Success

from yutto.exceptions import NoAccessPermissionError, NotFoundError, WrongArgumentError
from yutto.media import BangumiSeason, CheeseSeason
from yutto.parser import parse
from yutto.source import (
    AmbiguousSource,
    BangumiEpisodeSource,
    BangumiSeasonSource,
    CheeseEpisodeSource,
    CheeseSeasonSource,
    SourceOptions,
    UgcCollectionSource,
    UgcFavSource,
    UgcSeriesSource,
    UgcSpaceSource,
    UgcVideoSource,
    UgcWatchLaterSource,
)
from yutto.types import EpisodeId, MediaId, SeasonId

_NOT_FOUND = {"code": -404, "message": "啥都木有"}
_DEFAULT_OPTIONS = SourceOptions()


def _parse(value: str) -> Any:
    return parse(value)


def _episode_source(episode_id: EpisodeId) -> AmbiguousSource:
    return AmbiguousSource(
        id=episode_id,
        candidates=(
            BangumiEpisodeSource(id=episode_id),
            CheeseEpisodeSource(id=episode_id),
        ),
    )


def _season_source(season_id: SeasonId) -> AmbiguousSource:
    return AmbiguousSource(
        id=season_id,
        candidates=(
            BangumiSeasonSource(id=season_id),
            CheeseSeasonSource(id=season_id),
        ),
    )


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
                    "bvid": f"BV1{i}",
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
                    "title": f"第{i+1}节",
                    "cid": 200 + i,
                    "aid": 300 + i,
                    "cover": f"https://img/{i}.jpg",
                    "release_date": 1700000000 + i,
                }
                for i, episode_id in enumerate(episode_ids)
            ],
        },
    }


def _install_fetcher_stub(
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[str, Any],
) -> list[str]:
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


def test_parse_b23_semantic_urls() -> None:
    assert isinstance(_parse("https://b23.tv/BV1XK421y7ZL"), UgcVideoSource)
    assert isinstance(_parse("https://b23.tv/av123"), UgcVideoSource)
    assert isinstance(_parse("https://b23.tv/ep123"), BangumiEpisodeSource)
    assert isinstance(_parse("https://b23.tv/ss456"), BangumiSeasonSource)


def test_parse_ugc_container_urls() -> None:
    assert isinstance(_parse("https://space.bilibili.com/123/favlist?fid=456"), UgcFavSource)
    assert isinstance(
        _parse("https://space.bilibili.com/123/favlist?fid=456&ftype=collect"),
        UgcCollectionSource,
    )
    assert isinstance(
        _parse("https://space.bilibili.com/123/lists/456?type=series"),
        UgcSeriesSource,
    )
    assert isinstance(
        _parse("https://space.bilibili.com/123/lists/456?type=season"),
        UgcCollectionSource,
    )
    assert isinstance(_parse("https://space.bilibili.com/123/video"), UgcSpaceSource)
    assert isinstance(_parse("https://www.bilibili.com/list/watchlater"), UgcWatchLaterSource)


def test_parse_bare_ids_route_to_agnostic_sources() -> None:
    source = _parse("ep779775")
    assert isinstance(source, AmbiguousSource)
    assert source.id == EpisodeId("779775")

    source = _parse("ss34184")
    assert isinstance(source, AmbiguousSource)
    assert source.id == SeasonId("34184")

    assert not isinstance(_parse("ss34184"), (BangumiSeasonSource, CheeseSeasonSource))
    assert isinstance(_parse("md789"), BangumiSeasonSource)


def test_bangumi_episode_source_single_request_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fetcher_stub(
        monkeypatch,
        {"pgc/view/web/season": _bangumi_season_response("123")},
    )

    episode = asyncio.run(
        BangumiEpisodeSource(id=EpisodeId("123")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
    )

    assert isinstance(episode, BangumiSeason)
    assert episode.items[0].episode_id == EpisodeId("123")
    assert episode.items[0].extraMetaData is None
    assert len(calls) == 1
    assert "ep_id=123" in calls[0]


def test_bangumi_episode_source_initializes_metadata_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {"pgc/view/web/season": _bangumi_season_response("123")},
    )

    episode = asyncio.run(
        BangumiEpisodeSource(id=EpisodeId("123")).resolve(
            None,  # type: ignore[arg-type]
            SourceOptions(require_metadata=True),
        )
    )

    assert episode.items[0].extraMetaData is not None


def test_cheese_episode_source_rejects_quirk_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {"pugv/view/web/season": _cheese_season_response("999")},
    )

    with pytest.raises(NotFoundError):
        asyncio.run(
            CheeseEpisodeSource(id=EpisodeId("779775")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
        )


def test_episode_source_resolves_when_only_bangumi_has_it(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _bangumi_season_response("779775"),
            "pugv/view/web/season": _NOT_FOUND,
        },
    )

    episode = asyncio.run(
        _episode_source(EpisodeId("779775")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
    )

    assert isinstance(episode, BangumiSeason)
    assert episode.items[0].episode_id == EpisodeId("779775")
    assert len(calls) == 2


def test_episode_source_resolves_when_only_cheese_has_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _NOT_FOUND,
            "pugv/view/web/season": _cheese_season_response("779775"),
        },
    )

    episode = asyncio.run(
        _episode_source(EpisodeId("779775")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
    )

    assert isinstance(episode, CheeseSeason)
    assert episode.items[0].episode_id == EpisodeId("779775")


def test_episode_source_raises_when_both_namespaces_have_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _bangumi_season_response("779775"),
            "pugv/view/web/season": _cheese_season_response("779775"),
        },
    )

    with pytest.raises(WrongArgumentError):
        asyncio.run(
            _episode_source(EpisodeId("779775")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
        )


def test_episode_source_raises_when_neither_namespace_has_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _NOT_FOUND,
            "pugv/view/web/season": _NOT_FOUND,
        },
    )

    with pytest.raises(NotFoundError):
        asyncio.run(
            _episode_source(EpisodeId("999999")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
        )


def test_episode_source_propagates_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": {"code": -403, "message": "请求被拦截"},
            "pugv/view/web/season": _NOT_FOUND,
        },
    )

    with pytest.raises(NoAccessPermissionError):
        asyncio.run(
            _episode_source(EpisodeId("123")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
        )


def test_episode_source_prefers_success_over_other_namespace_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _bangumi_season_response("123"),
            "pugv/view/web/season": {"code": -403, "message": "请求被拦截"},
        },
    )

    episode = asyncio.run(
        _episode_source(EpisodeId("123")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
    )

    assert isinstance(episode, BangumiSeason)


def test_season_source_resolves_bangumi_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _bangumi_season_response("123"),
            "pugv/view/web/season": _NOT_FOUND,
        },
    )

    season = asyncio.run(
        _season_source(SeasonId("34184")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
    )

    assert isinstance(season, BangumiSeason)
    assert season.season_id == SeasonId("34184")
    assert [item.episode_id for item in season.items] == [EpisodeId("123")]


def test_season_source_resolves_cheese_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _NOT_FOUND,
            "pugv/view/web/season": _cheese_season_response("1122054"),
        },
    )

    season = asyncio.run(
        _season_source(SeasonId("34184")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
    )

    assert isinstance(season, CheeseSeason)
    assert [item.episode_id for item in season.items] == [EpisodeId("1122054")]


def test_season_source_raises_when_both_namespaces_have_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _bangumi_season_response("123"),
            "pugv/view/web/season": _cheese_season_response("1122054"),
        },
    )

    with pytest.raises(WrongArgumentError):
        asyncio.run(
            _season_source(SeasonId("34184")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
        )


def test_season_source_raises_when_neither_namespace_has_it(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/view/web/season": _NOT_FOUND,
            "pugv/view/web/season": _NOT_FOUND,
        },
    )

    with pytest.raises(NotFoundError):
        asyncio.run(
            _season_source(SeasonId("999999")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
        )


def test_bangumi_season_source_resolves_media_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "pgc/review/user": {"code": 0, "result": {"media": {"season_id": 456}}},
            "pgc/view/web/season": _bangumi_season_response("123"),
        },
    )

    season = asyncio.run(
        BangumiSeasonSource(id=MediaId("789")).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
    )

    assert isinstance(season, BangumiSeason)
    assert season.season_id == SeasonId("456")
    assert [item.episode_id for item in season.items] == [EpisodeId("123")]


def test_bangumi_season_source_filters_extra_and_preview_before_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                    "bvid": "BV125",
                    "badge": "",
                    "share_copy": "番剧 特别篇",
                    "cover": "https://img/125.jpg",
                    "pub_time": 1700000125,
                }
            ],
        }
    ]
    _install_fetcher_stub(monkeypatch, {"pgc/view/web/season": response})

    season = asyncio.run(
        BangumiSeasonSource(id=SeasonId("456")).resolve(
            None,  # type: ignore[arg-type]
            SourceOptions(
                selection="1~-1",
                with_extra_episodes=True,
                skip_preview=True,
            ),
        )
    )

    assert [item.episode_id for item in season.items] == [EpisodeId("124"), EpisodeId("125")]
