from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

import yutto.__main__ as main_module
import yutto.cli.event_renderer as renderer_module
from yutto.cli.command import (
    download_layer_from_namespace,
    resolve_download_command,
    resolve_download_runtime_options,
)
from yutto.cli.compat import normalize_argv
from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoSettings
from yutto.core.events import DownloadProgress, DownloadStage, DownloadStageChanged
from yutto.core.execution import RequestExecutionScopeFactory
from yutto.core.operation import (
    ReportColor,
    ReportLevel,
    bind_download_report_sink,
    emit_download_report,
)

if TYPE_CHECKING:
    from pathlib import Path


def _parse(arguments: list[str]):
    return build_parser().parse_args(normalize_argv(arguments))


def test_download_parser_accepts_auth_file(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    args = _parse(["https://example.com", "--auth-file", str(auth_file)])

    assert args.auth_file == auth_file


def test_download_parser_rejects_auth_config(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    with pytest.raises(SystemExit) as exc_info:
        _parse(["https://example.com", "--auth-config", str(auth_file)])

    assert exc_info.value.code == 2


def test_download_parser_emits_no_runtime_defaults():
    args = _parse(["https://example.com"])

    assert not hasattr(args, "ffmpeg_path")
    assert not hasattr(args, "jobs")

    runtime = resolve_download_runtime_options(args, YuttoSettings())
    assert runtime.ffmpeg_path == "ffmpeg"
    assert runtime.jobs == 1


def test_download_runtime_accepts_ffmpeg_path_override():
    args = _parse(["https://example.com", "--ffmpeg-path", "/opt/ffmpeg/ffmpeg"])

    runtime = resolve_download_runtime_options(args, YuttoSettings())

    assert runtime.ffmpeg_path == "/opt/ffmpeg/ffmpeg"


def test_download_configures_ffmpeg_path_at_command_boundary(monkeypatch: pytest.MonkeyPatch):
    recorded: list[str] = []
    args = SimpleNamespace(
        command="download",
        source="BV1xx411c7mD",
        ffmpeg_path="/opt/ffmpeg/ffmpeg",
    )
    parser = SimpleNamespace(parse_args=lambda _args: args)

    class RecordingFFmpeg:
        @classmethod
        def setup_ffmpeg_path(cls, ffmpeg_path: str) -> None:
            recorded.append(ffmpeg_path)
            raise RuntimeError("stop after recording")

    monkeypatch.setattr(main_module, "build_parser", lambda: parser)
    monkeypatch.setattr(main_module, "load_config", lambda _config: YuttoSettings())
    monkeypatch.setattr(main_module.sys, "argv", ["yutto", "download"])
    monkeypatch.setattr(main_module, "FFmpeg", RecordingFFmpeg)

    with pytest.raises(RuntimeError, match="stop after recording"):
        main_module.main()

    assert recorded == ["/opt/ffmpeg/ffmpeg"]


def test_global_config_precedes_explicit_subcommand(tmp_path: Path):
    config = tmp_path / "yutto.toml"

    args = _parse(["--config", str(config), "auth", "status"])

    assert args.config == config
    assert args.command == "auth"
    assert args.auth_command == "status"


def test_global_config_precedes_implicit_download(tmp_path: Path):
    config = tmp_path / "yutto.toml"

    args = _parse(["--config", str(config), "BV1xx411c7mD"])

    assert args.config == config
    assert args.command == "download"
    assert args.source == "BV1xx411c7mD"


def test_unknown_leading_option_is_not_scanned_as_global_config():
    argv = ["--another-like-config", "something", "download", "BVxxx"]

    assert normalize_argv(argv) == ["download", *argv]


def test_download_request_rejects_non_positive_num_workers():
    args = _parse(["https://example.com", "--num-workers", "0"])

    with pytest.raises(ValidationError):
        resolve_download_command(download_layer_from_namespace(args), YuttoSettings())


def test_download_runtime_rejects_non_positive_jobs():
    args = _parse(["https://example.com", "--jobs", "0"])

    with pytest.raises(ValueError, match="jobs"):
        resolve_download_runtime_options(args, YuttoSettings())


def test_auth_commands_accept_auth_file(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    for command in ("login", "status", "logout"):
        args = build_parser().parse_args(["auth", command, "--auth-file", str(auth_file)])
        assert args.command == "auth"
        assert args.auth_command == command
        assert args.auth_file == auth_file


def test_auth_login_rejects_auth_config(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["auth", "login", "--auth-config", str(auth_file)])

    assert exc_info.value.code == 2


def test_legacy_top_level_login_is_rewritten_to_auth():
    args = build_parser().parse_args(normalize_argv(["login"]))

    assert args.command == "auth"
    assert args.auth_command == "login"


def test_progress_renderer_respects_no_progress(monkeypatch: pytest.MonkeyPatch):
    rendered: list[str] = []
    debug_messages: list[str] = []
    monkeypatch.setattr(renderer_module, "get_terminal_size", lambda: (80, 24))
    monkeypatch.setattr(renderer_module.Logger.status, "set", rendered.append)
    monkeypatch.setattr(renderer_module.Logger, "debug", debug_messages.append)
    progress = DownloadProgress(
        current=1024,
        total=2048,
        speed_per_second=1024,
        buffered_bytes=512,
        is_congested=True,
    )

    renderer_module.CliApplicationEventRenderer(progress_enabled=False).emit(progress)
    assert rendered == []
    assert debug_messages == []

    renderer_module.CliApplicationEventRenderer().emit(progress)
    assert len(rendered) == 1
    assert "1.00 KiB" in rendered[0]
    assert "2.00 KiB" in rendered[0]
    assert debug_messages == []


def test_progress_bar_renders_committed_buffered_and_remaining_segments(monkeypatch: pytest.MonkeyPatch):
    rendered_segments: list[tuple[str, object]] = []
    monkeypatch.setattr(
        renderer_module,
        "colored_string",
        lambda text, *, fore, **_: rendered_segments.append((text, fore)) or text,
    )

    assert renderer_module._render_bar(4, 2, 8, "cyan", "yellow", 8) == "━" * 8
    assert rendered_segments == [
        ("━" * 4, "cyan"),
        ("━" * 2, "yellow"),
        ("━" * 2, renderer_module.RGBColor(64, 64, 64)),
    ]

    rendered_segments.clear()
    renderer_module._render_bar(500_000_000, 1, 1_000_000_000, "cyan", "yellow", 50)
    assert rendered_segments == [
        ("━" * 25, "cyan"),
        ("╸", "yellow"),
        ("━" * 24, renderer_module.RGBColor(64, 64, 64)),
    ]

    rendered_segments.clear()
    renderer_module._render_bar(500_000_001, 0, 1_000_000_000, "cyan", "yellow", 50)
    assert rendered_segments == [
        ("━" * 25 + "╸", "cyan"),
        ("━" * 24, renderer_module.RGBColor(64, 64, 64)),
    ]

    rendered_segments.clear()
    renderer_module._render_bar(500_000_001, 1, 1_000_000_000, "cyan", "yellow", 50)
    assert rendered_segments == [
        ("━" * 25 + "╸", "cyan"),
        ("━" * 24, renderer_module.RGBColor(64, 64, 64)),
    ]

    rendered_segments.clear()
    renderer_module._render_bar(9, 1, 16, "cyan", "yellow", 8)
    assert rendered_segments == [
        ("━" * 5, "cyan"),
        ("━" * 3, renderer_module.RGBColor(64, 64, 64)),
    ]

    rendered_segments.clear()
    renderer_module._render_bar(8, 2, 16, "cyan", "yellow", 8)
    assert rendered_segments == [
        ("━" * 4, "cyan"),
        ("━", "yellow"),
        ("━" * 3, renderer_module.RGBColor(64, 64, 64)),
    ]


def test_progress_renderer_turns_only_buffered_segment_red(monkeypatch: pytest.MonkeyPatch):
    rendered_bars: list[tuple[object, ...]] = []
    monkeypatch.setattr(renderer_module, "get_terminal_size", lambda: (80, 24))
    monkeypatch.setattr(
        renderer_module,
        "_render_bar",
        lambda *args: rendered_bars.append(args) or "bar",
    )
    monkeypatch.setattr(renderer_module.Logger.status, "set", lambda _message: None)

    renderer = renderer_module.CliApplicationEventRenderer()
    renderer.emit(
        DownloadProgress(
            current=1024,
            total=2048,
            speed_per_second=1024,
            buffered_bytes=512,
            is_congested=False,
        )
    )
    renderer.emit(
        DownloadProgress(
            current=1024,
            total=2048,
            speed_per_second=1024,
            buffered_bytes=512,
            is_congested=True,
        )
    )

    assert rendered_bars == [
        (512, 512, 2048, "cyan", "yellow", 43),
        (512, 512, 2048, "cyan", "red", 43),
    ]


def test_progress_renderer_tracks_multiple_items_and_removes_completed_rows(monkeypatch: pytest.MonkeyPatch):
    rendered: list[tuple[str, str]] = []
    removed: list[str] = []
    monkeypatch.setattr(renderer_module, "get_terminal_size", lambda: (100, 24))
    monkeypatch.setattr(renderer_module.Logger.status, "set_line", lambda key, text: rendered.append((key, text)))
    monkeypatch.setattr(renderer_module.Logger.status, "remove_line", removed.append)
    monkeypatch.setattr(renderer_module.Logger.status, "next_tick", lambda: None)

    renderer = renderer_module.CliApplicationEventRenderer()
    renderer.emit(DownloadProgress(current=1, total=2, speed_per_second=3, item="视频一"))
    renderer.emit(DownloadProgress(current=2, total=4, speed_per_second=5, item="视频二"))
    renderer.emit(DownloadStageChanged(name=DownloadStage.POSTPROCESSING, item="视频一"))

    assert [key for key, _ in rendered] == ["视频一", "视频二"]
    assert "视频一" in rendered[0][1]
    assert "视频二" in rendered[1][1]
    assert removed == ["视频一"]


def test_progress_labels_are_truncated_by_terminal_width():
    assert renderer_module._truncate_label("short", 10) == "short"
    assert renderer_module._truncate_label("一二三四五六", 7) == "一二三…"


def test_progress_renderer_aligns_bars_for_different_label_widths(monkeypatch: pytest.MonkeyPatch):
    rendered: list[str] = []
    bar_widths: list[int] = []
    monkeypatch.setattr(renderer_module, "get_terminal_size", lambda: (100, 24))
    monkeypatch.setattr(
        renderer_module,
        "_render_bar",
        lambda *args: bar_widths.append(args[-1]) or "bar",
    )
    monkeypatch.setattr(renderer_module.Logger.status, "set_line", lambda _key, text: rendered.append(text))

    renderer = renderer_module.CliApplicationEventRenderer()
    for title in ("短标题", "中等长度标题", "这是一个普通长度标题", "这是一个超过固定列宽的占位标题"):
        renderer.emit(DownloadProgress(current=1, total=2, speed_per_second=3, item=title))

    assert bar_widths == [42, 42, 42, 42]
    assert [renderer_module.get_string_width(line[: line.index("bar")]) for line in rendered] == [21, 21, 21, 21]
    assert "…" in rendered[-1]


@pytest.mark.parametrize(
    ("terminal_width", "expected_label_width", "expected_bar_width"),
    [
        (100, 20, 42),
        (68, 20, 10),
        (67, 20, 0),
        (57, 20, 0),
        (56, 19, 0),
        (47, 10, 0),
        (46, 0, 0),
        (37, 0, 0),
    ],
)
def test_progress_renderer_compresses_bar_before_label(
    monkeypatch: pytest.MonkeyPatch,
    terminal_width: int,
    expected_label_width: int,
    expected_bar_width: int,
):
    rendered: list[str] = []
    bar_widths: list[int] = []
    monkeypatch.setattr(renderer_module, "get_terminal_size", lambda: (terminal_width, 24))
    monkeypatch.setattr(
        renderer_module,
        "_render_bar",
        lambda *args: bar_widths.append(args[-1]) or "bar",
    )
    monkeypatch.setattr(renderer_module.Logger.status, "set_line", lambda _key, text: rendered.append(text))
    monkeypatch.setattr(renderer_module, "size_format", lambda _: "1234567890")

    renderer = renderer_module.CliApplicationEventRenderer()
    renderer.emit(DownloadProgress(current=1, total=2, speed_per_second=3, item="短标题"))

    if expected_label_width:
        expected_label = f"{renderer_module._fit_label('短标题', expected_label_width)} "
        assert rendered[0].startswith(expected_label)
    else:
        expected_stats = f"{'1234567890':>{renderer_module.PROGRESS_SIZE_MIN_WIDTH}}/"
        assert rendered[0].startswith(expected_stats)
    assert bar_widths == ([expected_bar_width] if expected_bar_width else [])


def test_progress_renderer_avoids_wrapping_for_wide_stats(monkeypatch: pytest.MonkeyPatch):
    rendered: list[str] = []
    bar_widths: list[int] = []
    monkeypatch.setattr(renderer_module, "get_terminal_size", lambda: (112, 24))
    monkeypatch.setattr(
        renderer_module,
        "_render_bar",
        lambda *args: bar_widths.append(args[-1]) or "━" * args[-1],
    )
    monkeypatch.setattr(renderer_module, "colored_string", lambda text, **_: text)
    monkeypatch.setattr(renderer_module.Logger.status, "set_line", lambda _key, text: rendered.append(text))

    renderer = renderer_module.CliApplicationEventRenderer()
    renderer.emit(DownloadProgress(current=1, total=2, speed_per_second=3, item="短标题"))
    renderer.emit(DownloadProgress(current=1023, total=1023, speed_per_second=1023, item="另一个标题"))

    assert bar_widths == [50, 45]
    assert [renderer_module.get_string_width(line) for line in rendered] == [108, 112]


def test_run_download_scopes_report_renderer_and_cleans_up_on_cancel(monkeypatch: pytest.MonkeyPatch):
    output: list[tuple[str, object]] = []

    async def cancel_download(_application: object, _requests: object) -> None:
        emit_download_report("warning", ReportLevel.WARNING)
        emit_download_report("badge", badge="TAG", color=ReportColor.GREEN)
        raise asyncio.CancelledError

    monkeypatch.setattr(main_module.YuttoApplication, "download_all", cancel_download)
    monkeypatch.setattr(renderer_module.Logger, "warning", lambda message: output.append(("warning", message)))
    monkeypatch.setattr(
        renderer_module.Logger,
        "custom",
        lambda message, badge: output.append(("badge", (message, badge.text))),
    )
    monkeypatch.setattr(renderer_module.Logger.status, "reset", lambda: output.append(("cleared", True)))
    monkeypatch.setattr(renderer_module, "colored_string", lambda message, *, fore, **_: f"{fore}:{message}")

    emit_download_report("unbound")
    with bind_download_report_sink(lambda message, *_: output.append(("outer", message))):
        with pytest.raises(asyncio.CancelledError):
            main_module.run_download(RequestExecutionScopeFactory(), [], renderer_module.CliApplicationEventRenderer())
        emit_download_report("outer")

    assert output == [
        ("warning", "warning"),
        ("badge", ("green:badge", "TAG")),
        ("cleared", True),
        ("outer", "outer"),
    ]
