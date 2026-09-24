from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from yutto.api.player import PlayUrlInfo, SubtitleInfo, SubtitleTrack, TranslationLanguage
from yutto.core.operation import bind_download_report_sink
from yutto.media import UgcPage
from yutto.resource import ResourceManifest, resolve_resource_manifest
from yutto.scope import ROOT_SCOPE, Scope
from yutto.types import AId, CId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    import pytest

    from yutto.core.execution import ExecutionScope

_EXECUTION = cast("ExecutionScope", None)


def _scope(values: dict[str, object]) -> Scope:
    return Scope(values, parent=ROOT_SCOPE)


def test_ugc_resource_manifest_uses_page_aid(monkeypatch: pytest.MonkeyPatch) -> None:
    aid = AId("808982399")
    page = UgcPage(
        aid=aid,
        cid=CId(123),
        metadata=ItemMetaData(title="P1"),
    )
    calls: list[tuple[Any, ...]] = []

    async def fake_playurl(*args: Any) -> PlayUrlInfo:
        calls.append(args)
        return PlayUrlInfo(videos=(), audios=())

    async def fake_danmaku(*args: Any) -> tuple[str, list[str]]:
        calls.append(args)
        return "xml", ["https://example.test/danmaku.xml"]

    monkeypatch.setattr("yutto.resource.get_ugc_video_playurl", fake_playurl)
    monkeypatch.setattr("yutto.resource._resolve_danmaku", fake_danmaku)

    scope = _scope(
        {
            "source.value": "BV1D84y1t76J",
            "resource.subtitle": False,
            "resource.cover": False,
            "resource.chapter_info": False,
        }
    )
    manifest = asyncio.run(resolve_resource_manifest(_EXECUTION, page, scope))

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
        cid=CId(123),
        metadata=ItemMetaData(title="P1", thumb="https://example.test/cover.jpg"),
    )
    scope = _scope(
        {
            "source.value": "BV1D84y1t76J",
            "resource.video": False,
            "resource.audio": False,
            "resource.subtitle": False,
            "resource.danmaku": False,
            "resource.chapter_info": False,
        }
    )
    manifest = asyncio.run(resolve_resource_manifest(_EXECUTION, page, scope))

    assert manifest.cover_url == "https://example.test/cover.jpg"
    assert not hasattr(manifest, "cover_data")


def test_resource_resolution_returns_diagnostics_without_rendering_them(monkeypatch: pytest.MonkeyPatch) -> None:
    page = UgcPage(
        aid=AId("808982399"),
        cid=CId(123),
        metadata=ItemMetaData(title="P1"),
    )
    language = TranslationLanguage(code="en", title="English")

    async def fake_playurl(*_args: Any) -> PlayUrlInfo:
        return PlayUrlInfo(
            videos=(),
            audios=(),
            is_preview=True,
            translation_languages=(language,),
        )

    async def fake_subtitle_info(*_args: Any, **_kwargs: Any) -> SubtitleInfo:
        return SubtitleInfo(
            tracks=(SubtitleTrack(language="zh-CN", url="https://example.test/subtitle.json"),),
            invalid_languages=("ja-JP",),
        )

    monkeypatch.setattr("yutto.resource.get_ugc_video_playurl", fake_playurl)
    monkeypatch.setattr("yutto.resource.get_subtitle_info", fake_subtitle_info)

    reports: list[str] = []
    scope = _scope(
        {
            "source.value": "BV1D84y1t76J",
            "resource.danmaku": False,
            "resource.cover": False,
            "resource.chapter_info": False,
            "resource.ai_translation_language": "en",
        }
    )
    with bind_download_report_sink(lambda message, *_args: reports.append(message)):
        manifest = asyncio.run(resolve_resource_manifest(_EXECUTION, page, scope))

    assert reports == []
    assert manifest.translation_languages == (language,)
    assert manifest.is_preview is True
    assert manifest.invalid_subtitle_languages == ("ja-JP",)
    assert manifest.subtitles == (("zh-CN", "https://example.test/subtitle.json"),)
