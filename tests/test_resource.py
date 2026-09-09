from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from yutto.core.options import ResourceOptions
from yutto.media import UgcPage
from yutto.resource import ResourceManifest, resolve_resource_manifest
from yutto.types import BvId, CId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    import pytest

    from yutto.core.execution import ExecutionScope

_SCOPE = cast("ExecutionScope", None)


def test_ugc_resource_manifest_uses_page_avid(monkeypatch: pytest.MonkeyPatch) -> None:
    avid = BvId("BV1D84y1t76J")
    page = UgcPage(
        avid=avid,
        page=1,
        cid=CId(123),
        metadata=ItemMetaData(title="P1"),
    )
    calls: list[tuple[Any, ...]] = []

    async def fake_playurl(*args: Any) -> tuple[list[Any], list[Any]]:
        calls.append(args)
        return [], []

    async def fake_danmaku(*args: Any) -> tuple[str, list[str]]:
        calls.append(args)
        return "xml", ["https://example.test/danmaku.xml"]

    monkeypatch.setattr("yutto.resource.get_ugc_video_playurl", fake_playurl)
    monkeypatch.setattr("yutto.resource._resolve_danmaku", fake_danmaku)

    options = ResourceOptions(
        subtitle=False,
        cover=False,
        chapter_info=False,
    )
    manifest = asyncio.run(resolve_resource_manifest(_SCOPE, page, options))

    assert isinstance(manifest, ResourceManifest)
    assert page.avid == avid
    assert calls[0][1] == page.avid
    assert calls[0][2] == page.cid
    assert calls[1][1] == page.avid
    assert calls[1][2] == page.cid
    assert manifest.danmaku_urls == ("https://example.test/danmaku.xml",)


def test_resource_manifest_keeps_cover_as_url() -> None:
    page = UgcPage(
        avid=BvId("BV1D84y1t76J"),
        page=1,
        cid=CId(123),
        metadata=ItemMetaData(title="P1", thumb="https://example.test/cover.jpg"),
    )
    manifest = asyncio.run(
        resolve_resource_manifest(
            _SCOPE,
            page,
            ResourceOptions(video=False, audio=False, subtitle=False, danmaku=False, chapter_info=False),
        )
    )

    assert manifest.cover_url == "https://example.test/cover.jpg"
    assert not hasattr(manifest, "cover_data")
