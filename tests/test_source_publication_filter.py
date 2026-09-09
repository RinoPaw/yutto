from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any, cast

from returns.result import Success

from yutto.core.options import SourceOptions, source_options_from_request
from yutto.core.request import DownloadRequest
from yutto.media import UgcSeries, UgcSpace
from yutto.selection import parse_selection
from yutto.source import UgcSeriesSource, UgcSpaceSource
from yutto.types import MId, SeriesId
from yutto.utils.filter import PublicationTimeFilter

if TYPE_CHECKING:
    import pytest

_SCOPE = cast("Any", None)


def _filter(start: int, end: int) -> PublicationTimeFilter:
    return PublicationTimeFilter(
        start_time=datetime.datetime.fromtimestamp(start),
        end_time=datetime.datetime.fromtimestamp(end),
    )


def _video_response(bvid: str, title: str, pubdate: int) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
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


def test_request_builds_publication_filter_for_sources() -> None:
    request = DownloadRequest.model_validate(
        {
            "source": {"url": "BV1D84y1t76J"},
            "selection": {"start_time": "2024-01-01", "end_time": "2024-02-01"},
        }
    )

    publication_filter = source_options_from_request(request).publication_time_filter
    assert publication_filter is not None
    assert publication_filter.matches(int(datetime.datetime(2024, 1, 15).timestamp()))
    assert not publication_filter.matches(int(datetime.datetime(2024, 2, 15).timestamp()))


def test_ugc_batch_source_filters_by_resolved_publication_time(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
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
            return Success(_video_response("BVOLD", "旧视频", 100))
        if "/x/web-interface/view?bvid=BVKEEP" in url:
            return Success(_video_response("BVKEEP", "保留视频", 300))
        raise AssertionError(f"unexpected fetch url: {url}")

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    options = SourceOptions(
        selection=parse_selection("~"),
        publication_time_filter=_filter(200, 400),
    )

    result = asyncio.run(UgcSeriesSource(id=SeriesId("456")).resolve(_SCOPE, options))

    assert isinstance(result.media, UgcSeries)
    assert [video.metadata.title for video in result.media.items] == ["保留视频"]


def test_space_source_filters_and_stops_old_pages_before_video_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_get_wbi_img(scope: object) -> object:
        return object()

    def fake_encode_wbi(params: dict[str, Any], wbi_img: object) -> dict[str, Any]:
        return params

    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
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
                                {"bvid": "BVKEEP", "created": 300},
                                {"bvid": "BVOLD", "created": 100},
                            ]
                        },
                        "page": {"count": 60},
                    },
                }
            )
        if "/x/web-interface/view?bvid=BVKEEP" in url:
            return Success(_video_response("BVKEEP", "保留视频", 300))
        if "/x/web-interface/view?bvid=BVOLD" in url:
            raise AssertionError("old video should be filtered before resolving its details")
        raise AssertionError(f"unexpected fetch url: {url}")

    monkeypatch.setattr("yutto.source.get_wbi_img", fake_get_wbi_img)
    monkeypatch.setattr("yutto.source.encode_wbi", fake_encode_wbi)
    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)

    options = SourceOptions(
        selection=parse_selection("~"),
        publication_time_filter=_filter(200, 400),
    )
    result = asyncio.run(UgcSpaceSource(id=MId("123")).resolve(_SCOPE, options))

    assert isinstance(result.media, UgcSpace)
    assert [video.metadata.title for video in result.media.items] == ["保留视频"]
    assert sum("/x/space/wbi/arc/search" in url for url, _ in calls) == 1
