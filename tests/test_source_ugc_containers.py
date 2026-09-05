from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import pytest
from returns.result import Success

from yutto.core.options import SourceOptions
from yutto.selection import parse_selection
from yutto.source import UgcCollectionSource, UgcSeriesSource
from yutto.types import CollectionId, MId, SeriesId

_DEFAULT_OPTIONS = SourceOptions()


def _install_fetcher_stub(
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[str, dict[str, Any]],
) -> list[str]:
    calls: list[str] = []

    async def fake_fetch_json(scope: object, url: str) -> Success[dict[str, Any]]:
        calls.append(url)
        for fragment, response in routes.items():
            if fragment in url:
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
    media = asyncio.run(
        UgcSeriesSource(id=SeriesId("456")).resolve(None, options)  # type: ignore[arg-type]
    )

    assert media.metadata.title == "视频系列"
    assert len(media.items) == 1
    assert media.items[0].metadata.title == "第二个"
    assert [page.metadata.title for page in media.items[0].items] == ["P1", "P2"]
    assert all(page.metadata.owner == "UP" for page in media.items[0].items)
    assert all(page.metadata.tag == ["标签"] for page in media.items[0].items)
    assert all(page.avid == media.items[0].avid for page in media.items[0].items)

    tree = media.to_dict()
    assert tree["metadata"]["title"] == "视频系列"
    assert tree["items"][0]["metadata"]["title"] == "第二个"
    assert [page["metadata"]["title"] for page in tree["items"][0]["items"]] == ["P1", "P2"]
    assert tree["items"][0]["avid"] == "BVSECOND"

    assert any("mid=123" in call and "series_id=456" in call for call in calls)
    assert any("bvid=BVSECOND" in call for call in calls)
    assert any("/x/tag/archive/tags" in call for call in calls)
    assert not any("bvid=BVFIRST" in call for call in calls)


def test_collection_keeps_read_metadata_without_fetching_tags(monkeypatch: pytest.MonkeyPatch) -> None:
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

    media = asyncio.run(
        UgcCollectionSource(
            id=CollectionId("456"),
            owner_id=MId("123"),
        ).resolve(None, _DEFAULT_OPTIONS)  # type: ignore[arg-type]
    )

    assert media.metadata.title == "视频合集"
    assert len(media.items) == 1
    assert media.items[0].metadata.owner == "UP"
    assert media.items[0].metadata.plot == "简介"
    assert media.items[0].metadata.genre == ["知识"]
    assert media.items[0].metadata.tag == []
    assert [page.metadata.title for page in media.items[0].items] == ["P1", "P2"]
    assert any("/x/polymer/web-space/seasons_archives_list" in call for call in calls)
    assert not any("/x/tag/archive/tags" in call for call in calls)
    assert not any("seasons_series_detail" in call for call in calls)
