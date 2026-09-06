from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from returns.result import Success

from yutto.core.request import DownloadRequest
from yutto.download_manager import DownloadManager
from yutto.media import UgcVideo


def _ugc_response() -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
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


def test_manager_resolves_source_to_media_tree_and_deduplicates_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_json(scope: object, url: str, **kwargs: Any) -> Success[dict[str, Any]]:
        return Success(_ugc_response())

    async def fake_validate_user_info(scope: object, required: dict[str, bool]) -> bool:
        return True

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    monkeypatch.setattr("yutto.download_manager.validate_user_info", fake_validate_user_info)
    monkeypatch.setattr("yutto.download_manager.emit_download_event", lambda event: None)

    request = DownloadRequest.model_validate(
        {
            "source": {"url": "https://www.bilibili.com/video/BV1D84y1t76J?p=2"},
            "selection": {"episodes": "3,1,3"},
        }
    )

    outcome = asyncio.run(DownloadManager().resolve_request(cast(Any, None), request))

    assert isinstance(outcome.media, UgcVideo)
    assert outcome.media.metadata.title == "投稿"
    assert [page.page for page in outcome.media.items] == [3, 1]
    assert [page.metadata.title for page in outcome.media.items] == ["P3", "P1"]
