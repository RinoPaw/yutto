from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import yutto.cli.formats as formats_module
from yutto.cli.formats import FormatListingEntry, emit_grouped_manifest_report
from yutto.core.operation import ReportLevel, bind_download_report_sink
from yutto.resource import ResourceManifest
from yutto.stream_formats import emit_manifest_formats, format_manifest_lines

if TYPE_CHECKING:
    from yutto.downloader.selector import StreamSelection
    from yutto.types import AudioUrlMeta, VideoUrlMeta


def _manifest() -> ResourceManifest:
    video: VideoUrlMeta = {
        "url": "https://signed.example/video",
        "mirrors": [],
        "codec": "avc",
        "width": 1920,
        "height": 1080,
        "quality": 80,
    }
    audio: AudioUrlMeta = {
        "url": "https://signed.example/audio",
        "mirrors": [],
        "codec": "mp4a",
        "width": 0,
        "height": 0,
        "quality": 30280,
    }
    return ResourceManifest(videos=(video,), audios=(audio,))


def test_emit_manifest_formats_uses_download_report_channel() -> None:
    manifest = _manifest()
    reports: list[tuple[str, ReportLevel]] = []

    def sink(message: str, level: ReportLevel, _badge: str | None, _color: object) -> None:
        reports.append((message, level))

    with bind_download_report_sink(sink):
        emit_manifest_formats(manifest)

    assert reports == [(line, ReportLevel.INFO) for line in format_manifest_lines(manifest)]


def test_preview_group_reuses_shared_manifest_emitter(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    calls: list[tuple[ResourceManifest, StreamSelection | None]] = []

    monkeypatch.setattr(
        formats_module,
        "emit_manifest_formats",
        lambda emitted_manifest, selection=None: calls.append((emitted_manifest, selection)),
    )

    emit_grouped_manifest_report(
        (FormatListingEntry(index=1, title="P1", manifest=manifest),),
        total_items=1,
    )

    assert calls == [(manifest, None)]
