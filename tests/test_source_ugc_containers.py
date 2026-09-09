from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.core.options import SourceOptions
from yutto.exceptions import NotFoundError
from yutto.media import UgcCollection, UgcFav, UgcSeries
from yutto.selection import parse_selection
from yutto.source import UgcCollectionSource, UgcFavSource, UgcSeriesSource, UgcVideoSource
from yutto.types import BvId, CollectionId, FId, MId, SeriesId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

_DEFAULT_OPTIONS = SourceOptions()
_SCOPE = cast("ExecutionScope", None)


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


def _video_response(bvid: str, title: str, page_count: int) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "bvid": bvid,
            "title": title,
            "desc": "简介",
            "pic": "https://img/cover.jpg",
            "pubdate": 1700000000,
            "owner": {
                "mid": 123,
                "name": "UP",
                "face": "https://img/face.jpg",
            },
            "tname": "知识",
            "pages": [
                {
                    "cid": 100 + index,
                    "part": f"P{index + 1}",
                }
                for index in range(page_count)
            ],
        },
    }


def test_ugc_video_expected_failure_is_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    error = NotFoundError("视频已失效")

    async def fail_info(scope: object, avid: object) -> tuple[object, dict[str, Any]]:
        raise error

    monkeypatch.setattr(UgcVideoSource, "get_ugc_video_info", fail_info)

    result = asyncio.run(UgcVideoSource(id=BvId("BVBAD")).resolve(_SCOPE, _DEFAULT_OPTIONS))

    assert result.media is None
    assert len(result.failures) == 1
    assert result.failures[0].index == 1
    assert result.failures[0].source == BvId("BVBAD")
    assert result.failures[0].error is error


def test_series_selects_video_then_resolves_all_pages_with_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fetcher_stub(
        monkeypatch,
        {
            "/x/series/series": {
                "code": 0,
                "data": {"meta": {"mid": 123, "name": "视频系列"}},
            },
            "/x/series/archives": {
                "code": 0,
                "data": {
                    "archives": [
                        {"bvid": "BVFIRST", "title": "第一个"},
                        {"bvid": "BVSECOND", "title": "第二个"},
                    ]
                },
            },
            "/x/tag/archive/tags": {
                "code": 0,
                "data": [{"tag_name": "标签"}],
            },
            "/x/web-interface/view?bvid=BVSECOND": _video_response("BVSECOND", "第二个", 2),
        },
    )

    options = replace(
        _DEFAULT_OPTIONS,
        selection=parse_selection("2"),
        fetch_tags=True,
    )
    result = asyncio.run(UgcSeriesSource(id=SeriesId("456")).resolve(_SCOPE, options))

    assert isinstance(result.media, UgcSeries)
    assert result.failures == ()
    assert result.media.metadata.title == "视频系列"
    assert len(result.media.items) == 1
    assert result.media.items[0].metadata.title == "第二个"
    assert [page.metadata.title for page in result.media.items[0].items] == ["P1", "P2"]
    assert all(page.metadata.owner == "UP" for page in result.media.items[0].items)
    assert all(page.metadata.tag == ["标签"] for page in result.media.items[0].items)
    assert all(page.avid == BvId("BVSECOND") for page in result.media.items[0].items)

    assert any("mid=123" in call and "series_id=456" in call for call in calls)
    assert any("bvid=BVSECOND" in call for call in calls)
    assert any("/x/tag/archive/tags" in call for call in calls)
    assert not any("bvid=BVFIRST" in call for call in calls)


def test_collection_uses_archives_metadata_and_resolves_selected_video(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install_fetcher_stub(
        monkeypatch,
        {
            "/x/polymer/web-space/seasons_archives_list": {
                "code": 0,
                "data": {
                    "meta": {"mid": 123, "name": "视频合集"},
                    "archives": [
                        {"bvid": "BVFIRST", "title": "合集视频"},
                    ],
                },
            },
            "/x/web-interface/view?bvid=BVFIRST": _video_response("BVFIRST", "合集视频", 2),
        },
    )

    result = asyncio.run(
        UgcCollectionSource(
            id=CollectionId("456"),
            owner_id=MId("123"),
        ).resolve(_SCOPE, _DEFAULT_OPTIONS)
    )

    assert isinstance(result.media, UgcCollection)
    assert result.media.metadata.title == "视频合集"
    assert len(result.media.items) == 1
    assert result.media.items[0].metadata.owner == "UP"
    assert result.media.items[0].metadata.plot == "简介"
    assert result.media.items[0].metadata.genre == ["知识"]
    assert result.media.items[0].metadata.tag == []
    assert [page.metadata.title for page in result.media.items[0].items] == ["P1", "P2"]
    assert all(page.avid == BvId("BVFIRST") for page in result.media.items[0].items)
    assert any("/x/polymer/web-space/seasons_archives_list" in call for call in calls)
    assert not any("/x/tag/archive/tags" in call for call in calls)
    assert not any("seasons_series_detail" in call for call in calls)


def test_favourite_preserves_folder_owner_and_item_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "/x/v3/fav/folder/info": {
                "code": 0,
                "data": {
                    "title": "收藏夹",
                    "intro": "收藏夹简介",
                    "cover": "https://img/fav.jpg",
                    "upper": {"mid": 999, "name": "收藏者"},
                },
            },
            "/x/v3/fav/resource/list": {
                "code": 0,
                "data": {
                    "medias": [
                        {"bvid": "BVSINGLE", "title": "收藏里的单P标题"},
                        {"bvid": "BVMULTI", "title": "收藏里的多P标题"},
                    ],
                    "has_more": False,
                },
            },
            "/x/web-interface/view?bvid=BVSINGLE": _video_response("BVSINGLE", "原始单P标题", 1),
            "/x/web-interface/view?bvid=BVMULTI": _video_response("BVMULTI", "原始多P标题", 2),
        },
    )
    options = replace(_DEFAULT_OPTIONS, selection=parse_selection("1~2"))

    result = asyncio.run(UgcFavSource(id=FId("456")).resolve(_SCOPE, options))

    assert isinstance(result.media, UgcFav)
    assert result.media.metadata.owner == "收藏者"
    assert result.media.metadata.mid == MId("999")
    assert [video.metadata.title for video in result.media.items] == ["收藏里的单P标题", "收藏里的多P标题"]
    assert result.media.items[0].metadata.show_title == "原始单P标题"
    assert result.media.items[0].items[0].metadata.title == "收藏里的单P标题"
    assert result.media.items[0].items[0].metadata.show_title == "收藏里的单P标题"
    assert [page.metadata.title for page in result.media.items[1].items] == ["P1", "P2"]
    assert all(page.metadata.show_title == "原始多P标题" for page in result.media.items[1].items)


def test_series_keeps_successes_and_records_expected_child_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "/x/series/series": {
                "code": 0,
                "data": {"meta": {"mid": 123, "name": "视频系列"}},
            },
            "/x/series/archives": {
                "code": 0,
                "data": {
                    "archives": [
                        {"bvid": "BVFIRST", "title": "第一个"},
                        {"bvid": "BVBAD", "title": "已失效"},
                        {"bvid": "BVTHIRD", "title": "第三个"},
                    ]
                },
            },
            "/x/web-interface/view?bvid=BVFIRST": _video_response("BVFIRST", "第一个", 1),
            "/x/web-interface/view?bvid=BVBAD": NotFoundError("视频已失效"),
            "/x/web-interface/view?bvid=BVTHIRD": _video_response("BVTHIRD", "第三个", 1),
        },
    )
    options = replace(_DEFAULT_OPTIONS, selection=parse_selection("1~3"))

    result = asyncio.run(UgcSeriesSource(id=SeriesId("456")).resolve(_SCOPE, options))

    assert isinstance(result.media, UgcSeries)
    assert [video.metadata.title for video in result.media.items] == ["第一个", "第三个"]
    assert len(result.failures) == 1
    assert result.failures[0].index == 2
    assert result.failures[0].source == BvId("BVBAD")
    assert isinstance(result.failures[0].error, NotFoundError)


def test_series_programming_error_aborts_task_group(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fetcher_stub(
        monkeypatch,
        {
            "/x/series/series": {
                "code": 0,
                "data": {"meta": {"mid": 123, "name": "视频系列"}},
            },
            "/x/series/archives": {
                "code": 0,
                "data": {
                    "archives": [
                        {"bvid": "BVFIRST", "title": "第一个"},
                        {"bvid": "BVBROKEN", "title": "坏数据"},
                    ]
                },
            },
            "/x/web-interface/view?bvid=BVFIRST": _video_response("BVFIRST", "第一个", 1),
            "/x/web-interface/view?bvid=BVBROKEN": TypeError("programming error"),
        },
    )
    options = replace(_DEFAULT_OPTIONS, selection=parse_selection("1~2"))

    with pytest.raises(TypeError, match="programming error"):
        asyncio.run(UgcSeriesSource(id=SeriesId("456")).resolve(_SCOPE, options))
