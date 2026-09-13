from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from returns.result import Success

from yutto.media import UgcAllFavourites
from yutto.parser import parse
from yutto.source import SourceOptions, UgcAllFavouritesSource, UgcFavSource
from yutto.types import MId

if TYPE_CHECKING:
    import pytest

_SCOPE = cast("Any", None)


def _video_response() -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "aid": 123,
            "bvid": "BVSINGLE",
            "title": "原始标题",
            "desc": "简介",
            "pic": "https://img/cover.jpg",
            "pubdate": 300,
            "owner": {"mid": 123, "name": "收藏者", "face": "https://img/face.jpg"},
            "tname": "知识",
            "pages": [{"cid": 101, "part": "P1", "duration": 10}],
        },
    }


def test_bare_favlist_parses_as_all_favourites() -> None:
    source = parse("https://space.bilibili.com/123/favlist")
    assert isinstance(source, UgcAllFavouritesSource)
    assert source.id == MId("123")

    source = parse("https://space.bilibili.com/123/favlist?fid=456")
    assert isinstance(source, UgcFavSource)


def test_all_favourites_resolves_every_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        calls.append(url)
        if "/x/v3/fav/folder/created/list-all" in url:
            return Success({"code": 0, "data": {"list": [{"id": 11}, {"id": 22}]}})
        if "/x/v3/fav/folder/info" in url:
            return Success(
                {
                    "code": 0,
                    "data": {
                        "title": "收藏夹",
                        "intro": "",
                        "cover": "",
                        "upper": {"mid": 123, "name": "收藏者"},
                    },
                }
            )
        if "/x/v3/fav/resource/list" in url:
            return Success(
                {
                    "code": 0,
                    "data": {
                        "medias": [{"bvid": "BVSINGLE", "title": "收藏标题"}],
                        "has_more": False,
                    },
                }
            )
        if "/x/web-interface/view?bvid=BVSINGLE" in url:
            return Success(_video_response())
        raise AssertionError(f"unexpected fetch url: {url}")

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)

    result = asyncio.run(UgcAllFavouritesSource(id=MId("123")).resolve(_SCOPE, SourceOptions()))

    assert isinstance(result.media, UgcAllFavourites)
    assert [favourite.fid.value for favourite in result.media.items] == ["11", "22"]
    assert all(len(favourite.items) == 1 for favourite in result.media.items)
    assert result.media.metadata.owner == "收藏者"
    assert result.failures == ()
    assert sum("/x/v3/fav/resource/list" in call for call in calls) == 2
