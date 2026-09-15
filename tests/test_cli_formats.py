from __future__ import annotations

import pytest

import yutto.__main__ as main_module
from yutto.cli.compat import normalize_argv
from yutto.cli.formats import build_format_probe_request, format_manifest_lines
from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoSettings
from yutto.core.request import DownloadRequest
from yutto.resource import ResourceManifest
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
