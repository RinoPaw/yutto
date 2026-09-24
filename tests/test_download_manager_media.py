from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from returns.result import Success

from yutto.download_manager import DownloadManager
from yutto.exceptions import NotFoundError
from yutto.media import MediaEntry, UgcPage, UgcSeries, UgcVideo
from yutto.scope import ROOT_SCOPE, Scope
from yutto.source import MediaResolveFailure, MediaResolveResult, MediaResolveStep
from yutto.types import AId, BvId, CId, SeriesId
from yutto.utils.metadata import ItemMetaData


def _ugc_response() -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "aid": 808982399,
            "bvid": "BV1D84y1t76J",
            "title": "投稿",
            "desc": "简介",
            "pic": "https://img/cover.jpg",
            "pubdate": 1_700_000_000,
            "pages": [
                {"cid": 101, "part": "P1", "duration": 10},
                {"cid": 102, "part": "P2", "duration": 20},
                {"cid": 103, "part": "P3", "duration": 30},
            ],
        },
    }


async def _allow_user_info(scope: object, required: dict[str, bool]) -> bool:
    return True


def _scope(values: dict[str, object] | None = None) -> Scope:
    return Scope(values or {"source.value": "fake-source"}, parent=ROOT_SCOPE)


def _install_manager_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yutto.download_manager.validate_user_info", _allow_user_info)
    monkeypatch.setattr("yutto.download_manager.emit_download_event", lambda event: None)


def _series_with_one_video() -> UgcSeries:
    aid = AId("123")
    return UgcSeries(
        series_id=SeriesId("456"),
        metadata=ItemMetaData(title="系列"),
        items=(
            MediaEntry(
                index=1,
                media=UgcVideo(
                    aid=aid,
                    metadata=ItemMetaData(title="可用视频"),
                    items=(
                        MediaEntry(
                            index=1,
                            media=UgcPage(aid=aid, cid=CId("101"), metadata=ItemMetaData(title="P1")),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_manager_resolves_source_to_media_tree_and_deduplicates_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        return Success(_ugc_response())

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    _install_manager_stubs(monkeypatch)

    scope = _scope(
        {
            "source.value": "https://www.bilibili.com/video/BV1D84y1t76J?p=2",
            "selection.expression": "3,1,3",
        }
    )
    result = asyncio.run(DownloadManager().resolve_scope(cast("Any", None), scope))

    assert isinstance(result.media, UgcVideo)
    assert result.media.metadata.title == "投稿"
    assert [entry.index for entry in result.media.items] == [3, 1]
    assert [entry.media.metadata.title for entry in result.media.items] == ["P3", "P1"]
    assert all(entry.media.aid == result.media.aid for entry in result.media.items)


def test_manager_keeps_partial_success_and_reports_child_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    error = NotFoundError("视频已失效")

    class FakeSource:
        async def resolve(self, execution: object, scope: Scope) -> MediaResolveResult:
            return MediaResolveResult(
                media=_series_with_one_video(),
                failures=(
                    MediaResolveFailure(
                        path=(MediaResolveStep(index=2, source=BvId("BVBAD")),),
                        error=error,
                    ),
                ),
            )

    reports: list[tuple[str, object]] = []
    monkeypatch.setattr("yutto.download_manager.parse", lambda value: FakeSource())
    monkeypatch.setattr(
        "yutto.download_manager.emit_download_report",
        lambda message, level=None, **kwargs: reports.append((message, level)),
    )
    _install_manager_stubs(monkeypatch)

    result = asyncio.run(DownloadManager().resolve_scope(cast("Any", None), _scope()))

    assert isinstance(result.media, UgcSeries)
    assert len(result.media.items) == 1
    assert result.failures[0].error is error
    assert any("第 2 项 BVBAD" in message and "视频已失效" in message for message, _ in reports)


def test_manager_keeps_all_child_failures_for_download(monkeypatch: pytest.MonkeyPatch) -> None:
    error = NotFoundError("视频已失效")

    class FakeSource:
        async def resolve(self, execution: object, scope: Scope) -> MediaResolveResult:
            return MediaResolveResult(
                media=UgcSeries(
                    series_id=SeriesId("456"),
                    metadata=ItemMetaData(title="系列"),
                    items=(),
                ),
                failures=(
                    MediaResolveFailure(
                        path=(MediaResolveStep(index=1, source=BvId("BVBAD")),),
                        error=error,
                    ),
                ),
            )

    monkeypatch.setattr("yutto.download_manager.parse", lambda value: FakeSource())
    monkeypatch.setattr("yutto.download_manager.emit_download_report", lambda *args, **kwargs: None)
    _install_manager_stubs(monkeypatch)

    result = asyncio.run(DownloadManager().resolve_scope(cast("Any", None), _scope()))

    assert isinstance(result.media, UgcSeries)
    assert result.media.items == ()
    assert result.failures[0].error is error


def test_manager_propagates_root_source_failure_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    error = NotFoundError("根列表不存在")

    class FakeSource:
        async def resolve(self, execution: object, scope: Scope) -> MediaResolveResult:
            raise error

    monkeypatch.setattr("yutto.download_manager.parse", lambda value: FakeSource())
    _install_manager_stubs(monkeypatch)

    with pytest.raises(NotFoundError) as raised:
        asyncio.run(DownloadManager().resolve_scope(cast("Any", None), _scope()))

    assert raised.value is error
