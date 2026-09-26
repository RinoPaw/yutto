from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from yutto.api.player import PlayUrlInfo, SubtitleInfo, SubtitleTrack, TranslationLanguage
from yutto.config import DEFAULT_CONFIG, ResolvedConfig, SourceSpec
from yutto.core.operation import bind_download_report_sink
from yutto.media import UgcPage
from yutto.resource import ResourceManifest, resolve_resource_manifest
from yutto.types import AId, CId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    import pytest

    from yutto.core.execution import ExecutionScope

_EXECUTION = cast("ExecutionScope", None)


def _config(**resource_updates: object) -> ResolvedConfig:
    return replace(
        DEFAULT_CONFIG,
        source=SourceSpec(value="BV1D84y1t76J"),
        resource=replace(DEFAULT_CONFIG.resource, **resource_updates),
    )


def test_ugc_resource_manifest_uses_page_aid(monkeypatch: pytest.MonkeyPatch) -> None:
    aid = AId("808982399")
    page = UgcPage(aid=aid, cid=CId(123), metadata=ItemMetaData(title="P1"))
    calls: list[tuple[Any, ...]] = []

    async def fake_playurl(*args: Any) -> PlayUrlInfo:
        calls.append(args)
        return PlayUrlInfo(videos=(), audios=())

    async def fake_danmaku(*args: Any) -> tuple[str, tuple[str, ...]]:
        calls.append(args)
        return "xml", ("https://example.test/danmaku.xml",)

    monkeypatch.setattr("yutto.resource.get_ugc_playurl", fake_playurl)
    monkeypatch.setattr("yutto.resource._resolve_danmaku", fake_danmaku)

    config = _config(subtitle=False, cover=False, chapter_info=False)
    manifest = asyncio.run(resolve_resource_manifest(_EXECUTION, page, config))

    assert isinstance(manifest, ResourceManifest)
    assert page.aid == aid
    assert calls[0][1] == page.aid
    assert calls[0][2] == page.cid
    assert calls[1][1] == page.aid
    assert calls[1][2] == page.cid
    assert manifest.video_requested is True
    assert manifest.audio_requested is True
    assert manifest.subtitle_requested is False
    assert manifest.danmaku_urls == ("https://example.test/danmaku.xml",)


def test_resource_manifest_distinguishes_unrequested_from_requested_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    page = UgcPage(aid=AId("808982399"), cid=CId(123), metadata=ItemMetaData(title="P1"))

    async def fake_playurl(*_args: Any) -> PlayUrlInfo:
        return PlayUrlInfo(videos=(), audios=())

    monkeypatch.setattr("yutto.resource.get_ugc_playurl", fake_playurl)
    common = {
        "audio": False,
        "subtitle": False,
        "danmaku": False,
        "cover": False,
        "chapter_info": False,
    }
    requested = asyncio.run(resolve_resource_manifest(_EXECUTION, page, _config(**common, video=True)))
    unrequested = asyncio.run(resolve_resource_manifest(_EXECUTION, page, _config(**common, video=False)))

    assert requested.video_requested is True
    assert requested.videos == ()
    assert unrequested.video_requested is False
    assert unrequested.videos == ()


def test_resource_manifest_keeps_cover_as_url() -> None:
    page = UgcPage(
        aid=AId("808982399"),
        cid=CId(123),
        metadata=ItemMetaData(title="P1", thumb="https://example.test/cover.jpg"),
    )
    config = _config(video=False, audio=False, subtitle=False, danmaku=False, chapter_info=False)
    manifest = asyncio.run(resolve_resource_manifest(_EXECUTION, page, config))

    assert manifest.cover_url == "https://example.test/cover.jpg"
    assert not hasattr(manifest, "cover_data")


def test_resource_resolution_returns_diagnostics_without_rendering_them(monkeypatch: pytest.MonkeyPatch) -> None:
    page = UgcPage(aid=AId("808982399"), cid=CId(123), metadata=ItemMetaData(title="P1"))
    language = TranslationLanguage(code="en", title="English")

    async def fake_playurl(*_args: Any) -> PlayUrlInfo:
        return PlayUrlInfo(videos=(), audios=(), is_preview=True, translation_languages=(language,))

    async def fake_subtitle_info(*_args: Any, **_kwargs: Any) -> SubtitleInfo:
        return SubtitleInfo(
            tracks=(SubtitleTrack(language="zh-CN", url="https://example.test/subtitle.json"),),
            invalid_languages=("ja-JP",),
        )

    monkeypatch.setattr("yutto.resource.get_ugc_playurl", fake_playurl)
    monkeypatch.setattr("yutto.resource.get_subtitle_info", fake_subtitle_info)

    reports: list[str] = []
    config = _config(danmaku=False, cover=False, chapter_info=False, ai_translation_language="en")
    with bind_download_report_sink(lambda message, *_args: reports.append(message)):
        manifest = asyncio.run(resolve_resource_manifest(_EXECUTION, page, config))

    assert reports == []
    assert manifest.translation_languages == (language,)
    assert manifest.is_preview is True
    assert manifest.invalid_subtitle_languages == ("ja-JP",)
    assert manifest.subtitles == (("zh-CN", "https://example.test/subtitle.json"),)
