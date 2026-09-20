from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

import yutto.__main__ as main_module
import yutto.server.command as server_command_module
from yutto.cli.compat import normalize_argv
from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoSettings
from yutto.core.operation import ReportLevel, emit_download_report
from yutto.exceptions import ErrorCode, WrongArgumentError
from yutto.server.command import build_server, resolve_server_token

if TYPE_CHECKING:
    from yutto.core.task_service import DownloadTaskService

pytestmark = pytest.mark.processor


def _server_options(**overrides: object) -> SimpleNamespace:
    values = {
        "request_settings": YuttoSettings(),
        "host": "127.0.0.1",
        "port": 11223,
        "allow_origin": (),
        "download_root": Path(),
        "tmp_root": None,
        "auth_file": None,
        "max_fetch_workers": 16,
        "max_download_workers": 16,
        "task_limit": 256,
        "jobs": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_serve_is_an_explicit_subcommand():
    assert normalize_argv(["serve"]) == ["serve"]
    args = build_parser().parse_args(["serve", "--port", "12345", "--allow-origin", "https://ui.example"])
    assert vars(args) == {
        "command": "serve",
        "port": 12345,
        "allow_origin": ["https://ui.example"],
    }


def test_serve_jobs_configures_download_runtime_workers():
    server = build_server(
        _server_options(jobs=3),
        "token",
        ffmpeg=cast("Any", SimpleNamespace(video_encodecs=(), audio_encodecs=())),
    )

    assert cast("DownloadTaskService", server._task_service).runtime.worker_count == 3


def test_serve_configures_ffmpeg_path_at_command_boundary(monkeypatch: pytest.MonkeyPatch):
    recorded: list[str] = []

    class RecordingFFmpeg:
        @classmethod
        def setup_ffmpeg_path(cls, ffmpeg_path: str) -> None:
            recorded.append(ffmpeg_path)
            raise RuntimeError("stop after recording")

    monkeypatch.setattr(server_command_module, "FFmpeg", RecordingFFmpeg)
    args = build_parser().parse_args(["serve", "--ffmpeg-path", "/opt/ffmpeg/ffmpeg"])
    with pytest.raises(RuntimeError, match="stop after recording"):
        server_command_module.run_server_command(args, YuttoSettings())

    assert recorded == ["/opt/ffmpeg/ffmpeg"]


def test_serve_argument_error_is_rendered_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    parser = SimpleNamespace(parse_args=lambda _args: SimpleNamespace(command="serve"))

    def fail_server(args: object, settings: YuttoSettings) -> None:
        raise WrongArgumentError("请配置正确的 FFmpeg 路径")

    monkeypatch.setattr(main_module, "build_parser", lambda: parser)
    monkeypatch.setattr(main_module, "search_for_settings_file", lambda: None)
    monkeypatch.setattr(main_module.sys, "argv", ["yutto", "serve"])
    monkeypatch.setattr(server_command_module, "run_server_command", fail_server)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == ErrorCode.WRONG_ARGUMENT_ERROR.value
    assert "请配置正确的 FFmpeg 路径" in captured.out
    assert "Traceback" not in captured.out + captured.err

    parser = SimpleNamespace(parse_args=lambda _args: SimpleNamespace(command="serve"))
    rendered_errors: list[str] = []

    def fail_server_with_report(args: object, settings: YuttoSettings) -> None:
        emit_download_report("server report", ReportLevel.ERROR)
        raise OSError("address already in use")

    monkeypatch.setattr(main_module, "build_parser", lambda: parser)
    monkeypatch.setattr(server_command_module, "run_server_command", fail_server_with_report)
    monkeypatch.setattr(main_module.Logger, "error", rendered_errors.append)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == ErrorCode.WRONG_ARGUMENT_ERROR.value
    assert rendered_errors == ["server report", "address already in use"]


def test_environment_token_takes_precedence(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("file-token\n", encoding="utf-8")

    resolved = resolve_server_token(token_file, environ={"YUTTO_SERVER_TOKEN": " environment-token "})

    assert resolved.value == "environment-token"
    assert resolved.generated is False
    assert resolved.persisted_to is None


def test_missing_token_file_is_created_with_a_generated_token(tmp_path):
    token_file = tmp_path / "private" / "server.token"

    resolved = resolve_server_token(token_file, environ={})

    assert resolved.generated is True
    assert resolved.persisted_to == token_file
    assert token_file.read_text(encoding="utf-8").strip() == resolved.value
    if os.name != "nt":
        assert token_file.stat().st_mode & 0o777 == 0o600


def test_empty_token_file_is_rejected(tmp_path):
    token_file = tmp_path / "empty.token"
    token_file.write_text("\n", encoding="utf-8")
    if os.name != "nt":
        token_file.chmod(0o600)

    with pytest.raises(ValueError, match="为空"):
        resolve_server_token(token_file, environ={})


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions only")
def test_existing_token_file_must_be_private_and_cannot_be_a_symlink(tmp_path):
    public_token = tmp_path / "public.token"
    public_token.write_text("secret\n", encoding="utf-8")
    public_token.chmod(0o644)
    with pytest.raises(ValueError, match="chmod 600"):
        resolve_server_token(public_token, environ={})

    private_token = tmp_path / "private.token"
    private_token.write_text("secret\n", encoding="utf-8")
    private_token.chmod(0o600)
    linked_token = tmp_path / "linked.token"
    linked_token.symlink_to(private_token)
    with pytest.raises(ValueError, match="安全读取"):
        resolve_server_token(linked_token, environ={})
