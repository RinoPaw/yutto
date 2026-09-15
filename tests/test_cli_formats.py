from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

import pytest

import yutto.__main__ as main_module
import yutto.cli.formats as formats_module
from yutto.cli.compat import normalize_argv
from yutto.cli.formats import (
    FormatListingEntry,
    build_format_probe_request,
    format_grouped_manifest_lines,
    format_index_ranges,
    format_manifest_lines,
)
from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoSettings
from yutto.core.request import DownloadRequest
from yutto.media import UgcPage
from yutto.resource import ResourceManifest
from yutto.types import AId, CId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AudioUrlMeta, VideoUrlMeta


def test_download_parser_accepts_list_formats():
    args = build_parser().parse_args(normalize_argv(["BV1xx411c7mD", "--list-formats"]))

    assert args.command == "download"
    assert args.list_formats is True


def test_format_probe_request_fetches_only_stream_resources():
    request = DownloadRequest.model_validate(
        {
            "source": {"url": "BV1xx411c7mD"},
            "resources": {
                "metadata": True,
                "ai_translation_language": "en",
            },
        }
    )

    probe = build_format_probe_request(request)

    assert probe.resources.video is True
    assert probe.resources.audio is True
    assert probe.resources.danmaku is False
    assert probe.resources.subtitle is False
    assert probe.resources.metadata is False
    assert probe.resources.cover is False
    assert probe.resources.chapter_info is False
    assert probe.resources.save_cover is False
    assert probe.resources.ai_translation_language == "en"
    assert request.resources.metadata is True
    assert request.resources.cover is True


def test_format_manifest_lines_show_quality_codec_and_resolution_without_urls():
    video: VideoUrlMeta = {
        "url": "https://signed.example/video",
        "mirrors": [],
        "codec": "hevc",
        "width": 3840,
        "height": 2160,
        "quality": 120,
    }
    audio: AudioUrlMeta = {
        "url": "https://signed.example/audio",
        "mirrors": [],
        "codec": "mp4a",
        "width": 0,
        "height": 0,
        "quality": 30280,
    }

    rendered = "\n".join(format_manifest_lines(ResourceManifest(videos=(video,), audios=(audio,))))

    assert "TYPE" in rendered
    assert "120" in rendered
    assert "hevc" in rendered
    assert "3840x2160" in rendered
    assert "4K 超高清" in rendered
    assert "30280" in rendered
    assert "mp4a" in rendered
    assert "320kbps" in rendered
    assert "signed.example" not in rendered


def test_format_manifest_lines_report_empty_manifest():
    assert format_manifest_lines(ResourceManifest()) == ("没有可用的视频或音频流。",)


def test_format_index_ranges_compacts_contiguous_and_sparse_pages():
    assert format_index_ranges([1, 2, 3, 5, 7, 8], prefix="P") == "P1-P3, P5, P7-P8"


def test_grouped_format_listing_merges_same_formats_even_when_urls_differ():
    manifests = []
    for index in range(1, 101):
        video: VideoUrlMeta = {
            "url": f"https://cdn{index}.example/video",
            "mirrors": [f"https://mirror{index}.example/video"],
            "codec": "hevc",
            "width": 3840,
            "height": 2160,
            "quality": 120,
        }
        audio: AudioUrlMeta = {
            "url": f"https://cdn{index}.example/audio",
            "mirrors": [],
            "codec": "mp4a",
            "width": 0,
            "height": 0,
            "quality": 30280,
        }
        manifests.append(ResourceManifest(videos=(video,), audios=(audio,)))

    entries = tuple(
        FormatListingEntry(
            index=index,
            title=f"P{index}",
            manifest=manifest,
            parent_key=42,
            parent_title="百P视频",
            page=index,
        )
        for index, manifest in enumerate(manifests, start=1)
    )

    rendered = "\n".join(format_grouped_manifest_lines(entries, total_items=100))

    assert "格式组 1/1（100 个条目）" in rendered
    assert "百P视频: P1-P100" in rendered
    assert rendered.count("TYPE") == 1
    assert "cdn1.example" not in rendered
    assert "cdn100.example" not in rendered


def test_grouped_format_listing_keeps_different_format_sets_separate():
    video_4k: VideoUrlMeta = {
        "url": "https://signed.example/4k",
        "mirrors": [],
        "codec": "hevc",
        "width": 3840,
        "height": 2160,
        "quality": 120,
    }
    video_1080p: VideoUrlMeta = {
        "url": "https://signed.example/1080p",
        "mirrors": [],
        "codec": "avc",
        "width": 1920,
        "height": 1080,
        "quality": 80,
    }
    entries = (
        FormatListingEntry(
            index=1,
            title="P1",
            manifest=ResourceManifest(videos=(video_4k,)),
            parent_key=42,
            parent_title="多P视频",
            page=1,
        ),
        FormatListingEntry(
            index=2,
            title="P2",
            manifest=ResourceManifest(videos=(video_1080p,)),
            parent_key=42,
            parent_title="多P视频",
            page=2,
        ),
    )

    rendered = "\n".join(format_grouped_manifest_lines(entries, total_items=2))

    assert "格式组 1/2（1 个条目）" in rendered
    assert "格式组 2/2（1 个条目）" in rendered
    assert "多P视频: P1" in rendered
    assert "多P视频: P2" in rendered
    assert rendered.count("TYPE") == 2


def test_format_manifest_resolution_respects_fetch_worker_limit(monkeypatch: pytest.MonkeyPatch):
    request = DownloadRequest.model_validate(
        {
            "source": {"url": "BV1xx411c7mD"},
            "network": {"fetch_workers": 2},
        }
    )
    items = tuple(
        UgcPage(
            metadata=ItemMetaData(title=f"P{index}"),
            aid=AId("1"),
            page=index,
            cid=CId(str(index)),
        )
        for index in range(1, 6)
    )
    active = 0
    max_active = 0

    async def fake_resolve_resource_manifest(
        _scope: object,
        _item: UgcPage,
        _request: DownloadRequest,
    ) -> ResourceManifest:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return ResourceManifest()

    monkeypatch.setattr(formats_module, "resolve_resource_manifest", fake_resolve_resource_manifest)

    outcomes = asyncio.run(
        formats_module.resolve_format_manifests(
            cast("ExecutionScope", object()),
            items,
            request,
        )
    )

    assert len(outcomes) == 5
    assert max_active == 2


def test_list_formats_mode_skips_ffmpeg_and_download(monkeypatch: pytest.MonkeyPatch):
    captured: list[list[DownloadRequest]] = []

    monkeypatch.setattr(main_module.sys, "argv", ["yutto", "BV1xx411c7mD", "--list-formats"])
    monkeypatch.setattr(main_module, "load_cli_settings", lambda _options: YuttoSettings())
    monkeypatch.setattr(main_module, "resolve_credentials", lambda _options: None)
    monkeypatch.setattr(
        main_module,
        "run_list_formats",
        lambda _scope_factory, requests, _renderer: captured.append(requests),
    )
    monkeypatch.setattr(
        main_module.FFmpeg,
        "setup_ffmpeg_path",
        lambda *_args: pytest.fail("--list-formats must not initialize FFmpeg"),
    )
    monkeypatch.setattr(
        main_module,
        "run_download",
        lambda *_args, **_kwargs: pytest.fail("--list-formats must not enter the download workflow"),
    )

    main_module.main()

    assert len(captured) == 1
    assert [request.source.url for request in captured[0]] == ["BV1xx411c7mD"]
