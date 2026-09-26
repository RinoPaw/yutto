from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from returns.result import Success

from yutto.config import DEFAULT_CONFIG, ResolvedConfig
from yutto.media import UgcSeries, UgcSpace
from yutto.source import UgcSeriesSource, UgcSpaceSource
from yutto.types import MId, SeriesId

if TYPE_CHECKING:
    import pytest

    from yutto.core.execution import ExecutionScope

_EXECUTION = cast("ExecutionScope", None)


def _config(*, since: int, before: int, expression: str = "~") -> ResolvedConfig:
    return replace(
        DEFAULT_CONFIG,
        selection=replace(
            DEFAULT_CONFIG.selection,
            expression=expression,
            published_since=since,
            published_before=before,
        ),
    )


def _video_response(aid: int, bvid: str, title: str, pubdate: int) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "aid": aid,
            "bvid": bvid,
            "title": title,
            "desc": "",
            "pic": "",
            "pubdate": pubdate,
            "owner": {"mid": 123, "name": "UP", "face": ""},
            "tname": "知识",
            "pages": [{"cid": 101, "part": title, "duration": 10}],
        },
    }


def test_ugc_batch_source_filters_by_resolved_publication_time(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(execution: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        if "/x/series/series" in url:
            return Success({"code": 0, "data": {"meta": {"mid": 123, "name": "系列"}}})
        if "/x/series/archives" in url:
            return Success(
                {
                    "code": 0,
                    "data": {
                        "archives": [{"bvid": "BVOLD"}, {"bvid": "BVKEEP"}],
                        "page": {"total": 2},
                    },
                }
            )
        if "/x/web-interface/view?bvid=BVOLD" in url:
            return Success(_video_response(100, "BVOLD", "旧视频", 1_704_067_200))
        if "/x/web-interface/view?bvid=BVKEEP" in url:
            return Success(_video_response(300, "BVKEEP", "保留视频", 1_706_745_600))
        if "/x/tag/archive/tags" in url:
            return Success({"code": 0, "data": []})
        raise AssertionError(f"unexpected fetch url: {url}")

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    result = asyncio.run(
        UgcSeriesSource(id=SeriesId("456")).resolve(
            _EXECUTION,
            _config(since=1_706_745_600, before=1_709_251_200),
        )
    )

    assert isinstance(result.media, UgcSeries)
    assert [entry.media.metadata.title for entry in result.media.items] == ["保留视频"]


def test_space_source_filters_before_selection_and_stops_old_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_get_wbi_img(execution: object) -> object:
        return object()

    def fake_encode_wbi(params: dict[str, Any], wbi_img: object) -> dict[str, Any]:
        return params

    async def fake_fetch_json(execution: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        calls.append((url, kwargs))
        if "/x/space/wbi/acc/info" in url:
            return Success({"code": 0, "data": {"name": "UP", "sign": "", "face": ""}})
        if "/x/space/wbi/arc/search" in url:
            pn = kwargs["params"]["pn"]
            if pn != 1:
                raise AssertionError("pagination should stop after the first page")
            return Success(
                {
                    "code": 0,
                    "data": {
                        "list": {
                            "vlist": [
                                {"bvid": "BVKEEP1", "created": 1_706_745_600},
                                {"bvid": "BVKEEP2", "created": 1_706_832_000},
                                {"bvid": "BVOLD", "created": 1_704_067_200},
                            ]
                        },
                        "page": {"count": 60},
                    },
                }
            )
        if "/x/web-interface/view?bvid=BVKEEP1" in url:
            return Success(_video_response(300, "BVKEEP1", "保留一", 1_706_745_600))
        if "/x/web-interface/view?bvid=BVKEEP2" in url:
            return Success(_video_response(301, "BVKEEP2", "保留二", 1_706_832_000))
        if "/x/web-interface/view?bvid=BVOLD" in url:
            raise AssertionError("old video should be filtered before resolving its details")
        if "/x/tag/archive/tags" in url:
            return Success({"code": 0, "data": []})
        raise AssertionError(f"unexpected fetch url: {url}")

    monkeypatch.setattr("yutto.api.ugc.get_wbi_img", fake_get_wbi_img)
    monkeypatch.setattr("yutto.api.ugc.encode_wbi", fake_encode_wbi)
    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)

    result = asyncio.run(
        UgcSpaceSource(id=MId("123")).resolve(
            _EXECUTION,
            _config(since=1_706_745_600, before=1_709_251_200, expression="2"),
        )
    )

    assert isinstance(result.media, UgcSpace)
    assert [entry.media.metadata.title for entry in result.media.items] == ["保留二"]
    assert sum("/x/space/wbi/arc/search" in url for url, _ in calls) == 1
