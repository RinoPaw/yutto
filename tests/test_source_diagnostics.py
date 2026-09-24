from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from returns.result import Success

from yutto.core.operation import bind_download_report_sink
from yutto.scope import ROOT_SCOPE, Scope
from yutto.source import MediaResolveDiagnostic, UgcVideoSource
from yutto.types import AvId

if TYPE_CHECKING:
    import pytest

    from yutto.core.execution import ExecutionScope

_EXECUTION = cast("ExecutionScope", None)


def test_source_returns_selection_diagnostics_without_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        if "/x/web-interface/view" in url:
            return Success(
                {
                    "code": 0,
                    "data": {
                        "aid": 808982399,
                        "bvid": "BV1D84y1t76J",
                        "title": "投稿",
                        "desc": "",
                        "pic": "",
                        "pubdate": 1700000000,
                        "pages": [
                            {"cid": 101, "part": "P1"},
                            {"cid": 102, "part": "P2"},
                            {"cid": 103, "part": "P3"},
                        ],
                    },
                }
            )
        if "/x/tag/archive/tags" in url:
            return Success({"code": 0, "data": []})
        raise AssertionError(f"unexpected fetch url: {url}")

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    reports: list[str] = []
    scope = Scope({"selection.expression": "3,5,1,3"}, parent=ROOT_SCOPE)
    with bind_download_report_sink(lambda message, *_args: reports.append(message)):
        result = asyncio.run(UgcVideoSource(id=AvId("808982399")).resolve(_EXECUTION, scope))

    assert reports == []
    assert result.diagnostics == (MediaResolveDiagnostic(total=3, out_of_range=(5,), empty=False),)
    assert [entry.index for entry in result.media.items] == [3, 1]
