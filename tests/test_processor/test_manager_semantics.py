from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from yutto.core.execution import ExecutionScope, RequestExecutionScopeFactory
from yutto.core.operation import bind_download_report_sink
from yutto.core.request import DownloadRequest
from yutto.core.result import DownloadResult, ItemResult, ItemState
from yutto.download_manager import DownloadManager, ensure_output_path_is_scoped, show_batch_episode_title
from yutto.exceptions import WrongArgumentError
from yutto.utils.functional import as_sync

if TYPE_CHECKING:
    from yutto.auth import AuthInfo

pytestmark = pytest.mark.processor


@as_sync
async def test_execute_uses_request_scopes_and_keeps_path_resolver_order():
    requests = [
        DownloadRequest.model_validate(
            {
                "source": {"url": "BV1first"},
                "access": {"auth_profile": "first"},
                "network": {"proxy": "no", "fetch_workers": 2, "download_workers": 3},
            }
        ),
        DownloadRequest.model_validate(
            {
                "source": {"url": "BV1second"},
                "access": {"auth_profile": "second"},
                "network": {"proxy": "auto", "fetch_workers": 5, "download_workers": 7},
            }
        ),
    ]

    class RecordingManager(DownloadManager):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[tuple[ExecutionScope, str, str]] = []

        async def process_request(
            self,
            scope: ExecutionScope,
            request: DownloadRequest,
        ) -> tuple[ItemResult, ...]:
            path = self.unique_path("same/video.mp4")
            self.calls.append((scope, request.source.url, path))
            return (ItemResult(state=ItemState.DONE, output_path=Path(path)),)

    def resolve_credentials(request: DownloadRequest) -> AuthInfo:
        return cast(
            "AuthInfo",
            {"SESSDATA": f"{request.access.auth_profile},session", "bili_jct": None},
        )

    manager = RecordingManager()
    result = await manager.execute(RequestExecutionScopeFactory(resolve_credentials), requests)

    assert [url for _, url, _ in manager.calls] == ["BV1first", "BV1second"]
    assert [Path(path) for _, _, path in manager.calls] == [
        Path("same/video.mp4"),
        Path("same/video (1).mp4"),
    ]
    first_scope, second_scope = (scope for scope, _, _ in manager.calls)
    assert first_scope is not second_scope
    assert first_scope.session is not second_scope.session
    assert first_scope.session.is_closed and second_scope.session.is_closed
    assert first_scope.fetch_limiter._value == 2
    assert first_scope.download_workers == 3
    assert second_scope.fetch_limiter._value == 5
    assert second_scope.download_workers == 7
    assert first_scope.fetch_limiter is not second_scope.fetch_limiter
    assert first_scope.session.cookie("SESSDATA") == "first%2Csession"
    assert second_scope.session.cookie("SESSDATA") == "second%2Csession"
    assert result == DownloadResult(
        items=(
            ItemResult(state=ItemState.DONE, output_path=Path("same/video.mp4")),
            ItemResult(state=ItemState.DONE, output_path=Path("same/video (1).mp4")),
        )
    )


@as_sync
async def test_execute_runs_requests_concurrently_and_preserves_result_order():
    requests = [
        DownloadRequest.model_validate({"source": {"url": "BV1first"}}),
        DownloadRequest.model_validate({"source": {"url": "BV1second"}}),
        DownloadRequest.model_validate({"source": {"url": "BV1third"}}),
    ]
    both_started = asyncio.Event()
    release = asyncio.Event()
    active = 0
    max_active = 0

    class ConcurrentManager(DownloadManager):
        def __init__(self) -> None:
            super().__init__(jobs=2)

        async def process_request(
            self,
            scope: ExecutionScope,
            request: DownloadRequest,
        ) -> tuple[ItemResult, ...]:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            if active == 2:
                both_started.set()
            try:
                await release.wait()
                return (ItemResult(state=ItemState.DONE, output_path=Path(request.source.url)),)
            finally:
                active -= 1

    manager = ConcurrentManager()
    execution = asyncio.create_task(manager.execute(RequestExecutionScopeFactory(), requests))
    await asyncio.wait_for(both_started.wait(), timeout=1)
    release.set()

    result = await execution

    assert [item.output_path for item in result.items] == [
        Path("BV1first"),
        Path("BV1second"),
        Path("BV1third"),
    ]
    assert max_active == 2


@as_sync
async def test_concurrent_execute_preserves_original_error_and_cancels_siblings():
    requests = [
        DownloadRequest.model_validate({"source": {"url": "BV1fail"}}),
        DownloadRequest.model_validate({"source": {"url": "BV1blocked"}}),
        DownloadRequest.model_validate({"source": {"url": "BV1must-not-start"}}),
    ]
    both_started = asyncio.Event()
    sibling_cancelled = asyncio.Event()
    started = 0
    calls: list[str] = []

    class FailingConcurrentManager(DownloadManager):
        def __init__(self) -> None:
            super().__init__(jobs=2)

        async def process_request(
            self,
            scope: ExecutionScope,
            request: DownloadRequest,
        ) -> tuple[ItemResult, ...]:
            nonlocal started
            calls.append(request.source.url)
            started += 1
            if started == 2:
                both_started.set()
            await both_started.wait()
            if request.source.url == "BV1fail":
                raise WrongArgumentError("request failed")
            try:
                await asyncio.Event().wait()
            finally:
                sibling_cancelled.set()
            return ()

    with pytest.raises(WrongArgumentError, match="request failed"):
        await FailingConcurrentManager().execute(RequestExecutionScopeFactory(), requests)

    assert sibling_cancelled.is_set()
    assert calls == ["BV1fail", "BV1blocked"]


@as_sync
async def test_execute_stops_on_failure_and_closes_session():
    requests = [
        DownloadRequest.model_validate({"source": {"url": "BV1first"}}),
        DownloadRequest.model_validate({"source": {"url": "BV1second"}}),
    ]

    class FailingManager(DownloadManager):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[str] = []
            self.session: Any = None

        async def process_request(
            self,
            scope: ExecutionScope,
            request: DownloadRequest,
        ) -> tuple[ItemResult, ...]:
            self.session = scope.session
            self.calls.append(request.source.url)
            raise WrongArgumentError("request failed")

    manager = FailingManager()
    with pytest.raises(WrongArgumentError, match="request failed"):
        await manager.execute(RequestExecutionScopeFactory(), requests)

    assert manager.calls == ["BV1first"]
    assert manager.session is not None and manager.session.is_closed


@as_sync
async def test_execute_cancellation_closes_session():
    started = asyncio.Event()
    release = asyncio.Event()
    request = DownloadRequest.model_validate({"source": {"url": "BV1cancel"}})

    class BlockingManager(DownloadManager):
        def __init__(self) -> None:
            super().__init__()
            self.session: Any = None

        async def process_request(
            self,
            scope: ExecutionScope,
            request: DownloadRequest,
        ) -> tuple[ItemResult, ...]:
            self.session = scope.session
            started.set()
            await release.wait()
            return ()

    manager = BlockingManager()
    execution = asyncio.create_task(manager.execute(RequestExecutionScopeFactory(), [request]))
    await started.wait()
    execution.cancel()

    with pytest.raises(asyncio.CancelledError):
        await execution

    assert manager.session is not None and manager.session.is_closed


def test_show_batch_episode_title_preserves_order_and_group_state():
    output: list[tuple[str, str]] = []

    def capture_output(message: str, _level: Any, badge: str | None, _color: Any) -> None:
        assert badge is not None
        output.append((message, badge))

    current_group: str | None = None
    group_states: list[str | None] = []
    items = [
        (Path("投稿 A/P1"), "投稿 A"),
        (Path("投稿 A/P2"), "投稿 A"),
        (Path("单集"), None),
        (Path("投稿 B/P1"), "投稿 B"),
    ]
    with bind_download_report_sink(capture_output):
        for index, (path, display_group) in enumerate(items, start=1):
            current_group = show_batch_episode_title(
                display_group,
                path,
                index,
                len(items),
                current_group,
            )
            group_states.append(current_group)

    assert group_states == ["投稿 A", "投稿 A", None, "投稿 B"]
    assert output == [
        ("投稿 A", "列表"),
        ("  P1", "[1/4]"),
        ("  P2", "[2/4]"),
        ("单集", "[3/4]"),
        ("投稿 B", "列表"),
        ("  P1", "[4/4]"),
    ]


def test_server_output_boundary_checks_final_rendered_path(tmp_path: Path):
    output_root = tmp_path / "output"
    temporary_root = tmp_path / "temporary"
    outside = tmp_path / "outside"
    output_root.mkdir()
    temporary_root.mkdir()
    outside.mkdir()

    ensure_output_path_is_scoped(Path("series/episode"), output_root, temporary_root)

    with pytest.raises(WrongArgumentError, match="超出了"):
        ensure_output_path_is_scoped(Path("../outside/episode"), output_root, temporary_root)
    with pytest.raises(WrongArgumentError, match="超出了"):
        ensure_output_path_is_scoped(Path("/outside/episode"), output_root, temporary_root)

    (output_root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WrongArgumentError, match="超出了"):
        ensure_output_path_is_scoped(Path("linked/episode"), output_root, temporary_root)
