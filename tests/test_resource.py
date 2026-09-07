from __future__ import annotations

import asyncio
from typing import Any

import pytest

from yutto.core.options import ResourceOptions
from yutto.media import UgcPage, UgcVideo
from yutto.resource import ResourceManifest, resolve_resource_manifest
from yutto.types import BvId, CId
from yutto.utils.metadata import ItemMetaData


def test_ugc_resource_manifest_uses_parent_video_avid(monkeypatch: pytest.MonkeyPatch) -> None:
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

    async def fake_danmaku_urls(*args: Any) -> tuple[str, list[str]]:
        calls.append(args)
        return "xml", ["https://example.test/danmaku.xml"]

    monkeypatch.setattr("yutto.resource.get_ugc_video_playurl", fake_playurl)
    monkeypatch.setattr("yutto.resource.resolve_danmaku_urls", fake_danmaku_urls)

    options = ResourceOptions(
        subtitle=False,
        cover=False,
        chapter_info=False,
    )
    manifest = asyncio.run(resolve_resource_manifest(None, video, page, options))  # type: ignore[arg-type]

    assert isinstance(manifest, ResourceManifest)
    assert not hasattr(page, "avid")
    assert calls[0][1] == video.avid
    assert calls[0][2] == page.cid
    assert calls[1][1] == page.cid
    assert calls[1][2] == video.avid
    assert manifest.danmaku_urls == ("https://example.test/danmaku.xml",)


def test_resource_manifest_keeps_cover_as_url() -> None:
    video = UgcVideo(
        avid=BvId("BV1D84y1t76J"),
        metadata=ItemMetaData(title="投稿"),
        items=[
            UgcPage(
                page=1,
                cid=CId(123),
                metadata=ItemMetaData(title="P1", thumb="https://example.test/cover.jpg"),
            )
        ],
    )
    manifest = asyncio.run(
        resolve_resource_manifest(
            None,  # type: ignore[arg-type]
            video,
            video.items[0],
            ResourceOptions(video=False, audio=False, subtitle=False, danmaku=False, chapter_info=False),
        )
    )

    assert manifest.cover_url == "https://example.test/cover.jpg"
    assert not hasattr(manifest, "cover_data")
