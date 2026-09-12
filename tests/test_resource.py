from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from yutto.core.request import DownloadRequest
from yutto.media import UgcPage
from yutto.resource import ResourceManifest, resolve_resource_manifest
from yutto.types import AId, CId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    import pytest

    from yutto.core.execution import ExecutionScope

_SCOPE = cast("ExecutionScope", None)


def test_ugc_resource_manifest_uses_page_aid(monkeypatch: pytest.MonkeyPatch) -> None:
    aid = AId("808982399")
    page = UgcPage(
        aid=aid,
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

    request = DownloadRequest.model_validate(
        {
            "source": {"url": "BV1D84y1t76J"},
            "resources": {
                "subtitle": False,
                "cover": False,
                "chapter_info": False,
            },
        }
    )
    manifest = asyncio.run(resolve_resource_manifest(_SCOPE, page, request))

    assert isinstance(manifest, ResourceManifest)
    assert page.aid == aid
    assert calls[0][1] == page.aid
    assert calls[0][2] == page.cid
    assert calls[1][1] == page.aid
    assert calls[1][2] == page.cid
    assert manifest.danmaku_urls == ("https://example.test/danmaku.xml",)


def test_resource_manifest_keeps_cover_as_url() -> None:
    page = UgcPage(
        aid=AId("808982399"),
        page=1,
        cid=CId(123),
        metadata=ItemMetaData(title="P1", thumb="https://example.test/cover.jpg"),
    )
    request = DownloadRequest.model_validate(
        {
            "source": {"url": "BV1D84y1t76J"},
            "resources": {
                "video": False,
                "audio": False,
                "subtitle": False,
                "danmaku": False,
                "chapter_info": False,
            },
        }
    )
    manifest = asyncio.run(resolve_resource_manifest(_SCOPE, page, request))

    assert manifest.cover_url == "https://example.test/cover.jpg"
    assert not hasattr(manifest, "cover_data")
