from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from returns.result import Success

import yutto.__main__ as main_module
import yutto.download_manager as download_manager_module
from yutto._native import InvalidUrlError
from yutto.core.execution import ExecutionScope
from yutto.core.request import DownloadRequest
from yutto.download_manager import DownloadManager
from yutto.exceptions import ErrorCode, NotLoginError, WrongUrlError, YuttoBaseException
from yutto.utils.fetcher import Fetcher
from yutto.utils.functional import as_sync

pytestmark = pytest.mark.processor


def make_request(url: str = "BV1structured") -> DownloadRequest:
    return DownloadRequest.model_validate({"source": {"url": url}})


def assert_error(error: YuttoBaseException, message: str, code: ErrorCode) -> None:
    assert str(error) == message
    assert error.message == message
    assert error.code is code


@as_sync
async def test_manager_raises_login_error(monkeypatch: pytest.MonkeyPatch):
    async def reject_login(scope: ExecutionScope, requirements: dict[str, bool]) -> bool:
        return False

    monkeypatch.setattr(download_manager_module, "validate_user_info", reject_login)
    with pytest.raises(NotLoginError) as exc_info:
        await DownloadManager().process_request(
            ExecutionScope(cast("Any", object())),
            make_request(),
        )

    assert_error(
        exc_info.value,
        "启用了严格校验大会员或登录模式，请检查认证信息（--auth）或大会员状态！",
        ErrorCode.NOT_LOGIN_ERROR,
    )


@as_sync
async def test_manager_raises_url_errors_without_network(monkeypatch: pytest.MonkeyPatch):
    async def reject_url(scope: ExecutionScope, url: str):
        raise InvalidUrlError("invalid")

    monkeypatch.setattr(Fetcher, "get_redirected_url", reject_url)
    with pytest.raises(WrongUrlError) as exc_info:
        await DownloadManager().process_request(
            ExecutionScope(cast("Any", object())),
            make_request("not-a-url"),
        )

    assert_error(
        exc_info.value,
        "无效的 url(not-a-url)～请检查一下链接是否正确～",
        ErrorCode.WRONG_URL_ERROR,
    )


@as_sync
async def test_manager_reports_unmatched_url_as_structured_error(monkeypatch: pytest.MonkeyPatch):
    async def keep_url(scope: ExecutionScope, url: str):
        return Success(url)

    monkeypatch.setattr(Fetcher, "get_redirected_url", keep_url)

    with pytest.raises(WrongUrlError) as exc_info:
        await DownloadManager().process_request(
            ExecutionScope(cast("Any", object())),
            make_request("https://example.com/unsupported"),
        )

    assert_error(
        exc_info.value,
        "无法识别 url（https://example.com/unsupported）",
        ErrorCode.WRONG_URL_ERROR,
    )


def configure_download_cli(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
    *,
    replace_logger: bool = True,
) -> tuple[list[str], list[str]]:
    parser = SimpleNamespace(
        parse_args=lambda args: SimpleNamespace(command="download", no_progress=True, jobs=1, ffmpeg_path="ffmpeg")
    )
    rendered_errors: list[str] = []
    rendered_info: list[str] = []

    def fail_download(
        scope_factory: object,
        requests: list[DownloadRequest],
        renderer: object,
        *,
        jobs: int,
    ):
        raise failure

    monkeypatch.setattr(main_module, "cli", lambda: parser)
    monkeypatch.setattr(main_module.sys, "argv", ["yutto", "BV1structured"])
    monkeypatch.setattr(main_module, "initial_validation", lambda args: None)
    monkeypatch.setattr(main_module.FFmpeg, "setup_ffmpeg_path", lambda path: None)
    monkeypatch.setattr(main_module, "flatten_args", lambda args, parser: [args])
    monkeypatch.setattr(main_module, "hydrate_auth", lambda args: None)
    monkeypatch.setattr(main_module, "download_request_from_namespace", lambda args: make_request())
    monkeypatch.setattr(main_module, "run_download", fail_download)
    if replace_logger:
        monkeypatch.setattr(
            main_module,
            "Logger",
            SimpleNamespace(error=rendered_errors.append, info=rendered_info.append),
        )
    return rendered_errors, rendered_info


def test_download_cli_renders_structured_error_once(monkeypatch: pytest.MonkeyPatch):
    message = "url 不正确呦～"
    rendered_errors, rendered_info = configure_download_cli(monkeypatch, WrongUrlError(message))

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == ErrorCode.WRONG_URL_ERROR.value
    assert rendered_errors == [message]
    assert rendered_info == []


def test_download_cli_renders_error_badge_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    message = "url 不正确呀～"
    configure_download_cli(monkeypatch, WrongUrlError(message), replace_logger=False)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == ErrorCode.WRONG_URL_ERROR.value
    assert "ERROR" in captured.out
    assert message in captured.out
    assert "Traceback" not in captured.out + captured.err


def test_download_cli_does_not_treat_system_exit_as_pause(monkeypatch: pytest.MonkeyPatch):
    rendered_errors, rendered_info = configure_download_cli(
        monkeypatch,
        SystemExit(ErrorCode.WRONG_ARGUMENT_ERROR.value),
    )

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == ErrorCode.WRONG_ARGUMENT_ERROR.value
    assert rendered_errors == []
    assert rendered_info == []


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), asyncio.CancelledError()])
def test_download_cli_keeps_pause_mapping(monkeypatch: pytest.MonkeyPatch, interruption: BaseException):
    rendered_errors, rendered_info = configure_download_cli(monkeypatch, interruption)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == ErrorCode.PAUSED_DOWNLOAD.value
    assert rendered_errors == []
    assert rendered_info == ["已终止下载，再次运行即可继续下载～"]
