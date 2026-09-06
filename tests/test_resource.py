from __future__ import annotations

import asyncio
from typing import Any

import pytest

from yutto.core.options import ResourceOptions
from yutto.media import UgcPage, UgcVideo
from yutto.resource import resolve_media_item
from yutto.types import BvId, CId
from yutto.utils.metadata import ItemMetaData


def test_ugc_resource_resolution_uses_parent_video_avid(monkeypatch: pytest.MonkeyPatch) -> None:
    video = UgcVideo(
        avid=BvId("BV1D84y1t76J"),
        metadata=ItemMetaData(title="投稿"),
        items=[UgcPage(page=1, cid=CId(123), metadata=ItemMetaData(title="P1"))],
    )
    page = video.items[0]
    calls: list[tuple[Any, ...]] = []

    async def fake_playurl(*args: Any) -> tuple[list[Any], list[Any]]:
        calls.append(args)
        return [], []

    async def fake_danmaku(*args: Any) -> dict[str, Any]:
        calls.append(args)
        return {"source_type": None, "save_type": None, "data": []}

    monkeypatch.setattr("yutto.resource.get_ugc_video_playurl", fake_playurl)
    monkeypatch.setattr("yutto.resource.get_danmaku", fake_danmaku)

    options = ResourceOptions(
        subtitle=False,
        cover=False,
        chapter_info=False,
    )
    asyncio.run(resolve_media_item(None, video, page, options))  # type: ignore[arg-type]

    assert not hasattr(page, "avid")
    assert calls[0][1] == video.avid
    assert calls[0][2] == page.cid
    assert calls[1][1] == page.cid
    assert calls[1][2] == video.avid
