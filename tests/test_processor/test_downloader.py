from __future__ import annotations

import asyncio
import inspect
import shutil
import sys
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Failure, Success

import yutto.downloader.transfer as transfer_module
from tests.helpers.http_range_server import LocalRangeServer, RangeFault
from yutto._native import TransferWorkerLimit
from yutto.core.events import DownloadEvent, DownloadProgress
from yutto.core.execution import ExecutionScope
from yutto.core.operation import bind_download_event_sink
from yutto.downloader.progressbar import show_progress
from yutto.downloader.transfer import _probe_media_size, _wait_for_native_transfers, download_files
from yutto.exceptions import MaxRetryError
from yutto.utils.fetcher import Fetcher, create_client
from yutto.utils.functional import as_sync

if TYPE_CHECKING:
    from pathlib import Path


pytestmark = pytest.mark.processor


async def download_one(
    scope: ExecutionScope,
    url: str,
    *,
    mirrors: tuple[str, ...] = (),
    block_size: int = 64 * 1024,
    banned_mirrors_pattern: str | None = None,
) -> Path:
    paths = await download_files(
        scope,
        ((url, mirrors),),
        block_size=block_size,
        banned_mirrors_pattern=banned_mirrors_pattern,
    )
    return paths[0]


def test_download_files_does_not_accept_a_destination_path():
    assert "staging_directory" not in inspect.signature(download_files).parameters


@pytest.mark.parametrize("capacity", [-1, 0, sys.maxsize])
def test_native_worker_limit_rejects_invalid_capacity(capacity: int):
    with pytest.raises(ValueError):
        TransferWorkerLimit(capacity)


@as_sync
async def test_local_range_server_targets_faults_and_closes_connections():
    with LocalRangeServer(b"payload", faults=[((2, 3), RangeFault.IGNORE)]) as server:
        async with create_client(trust_env=False) as session:
            probe = await session.get(server.url, headers={"Range": "bytes=0-1"})
            faulted = await session.get(server.url, headers={"Range": "bytes=2-3"})

    assert probe.status_code == 206
    assert faulted.status_code == 200
    assert probe.header("Connection") == "close"
    assert faulted.header("Connection") == "close"


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[DownloadEvent] = []

    def emit(self, event: DownloadEvent) -> None:
        self.events.append(event)


@as_sync
async def test_native_resume_progress_does_not_count_existing_bytes_as_speed():
    page_size = 64 * 1024

    class Snapshot:
        def __init__(
            self,
            origin_bytes: int,
            received_bytes: int,
            committed_bytes: int,
            *,
            window_saturated: bool = False,
        ):
            self.origin_bytes = origin_bytes
            self.received_bytes = received_bytes
            self.committed_bytes = committed_bytes
            self.window_saturated = window_saturated

    class Handle:
        snapshots = iter([Snapshot(0, 0, 0), Snapshot(page_size, page_size, page_size)])

        def snapshot(self) -> Snapshot:
            return next(self.snapshots)

        def done(self) -> bool:
            return True

    sink = RecordingEventSink()
    with bind_download_event_sink(sink):
        await show_progress([Handle()], page_size * 2, item="video")

    assert sink.events == [
        DownloadProgress(
            current=page_size,
            total=page_size * 2,
            speed_per_second=0,
            buffered_bytes=0,
            item="video",
        )
    ]


@pytest.mark.parametrize("window_saturated", [False, True])
@as_sync
async def test_native_progress_uses_only_window_saturation_signal(window_saturated: bool):
    page_size = 64 * 1024

    class Snapshot:
        origin_bytes = 0
        received_bytes = 3 * page_size
        committed_bytes = page_size

        def __init__(self) -> None:
            self.window_saturated = window_saturated

    class Handle:
        def snapshot(self) -> Snapshot:
            return Snapshot()

        def done(self) -> bool:
            return True

    sink = RecordingEventSink()
    with bind_download_event_sink(sink):
        await show_progress([Handle()], 8 * page_size)

    assert len(sink.events) == 1
    assert isinstance(sink.events[0], DownloadProgress)
    assert sink.events[0].buffered_bytes == 2 * page_size
    assert sink.events[0].is_congested is window_saturated


@as_sync
async def test_probe_media_size_preserves_probe_failures(monkeypatch: pytest.MonkeyPatch):
    failures = {
        "primary": MaxRetryError("primary failed"),
        "mirror": MaxRetryError("mirror failed"),
    }

    async def get_size(_scope: ExecutionScope, url: str) -> Failure[MaxRetryError]:
        return Failure(failures[url])

    monkeypatch.setattr(Fetcher, "get_size", get_size)
    scope = ExecutionScope(cast("Any", object()))
    with pytest.raises(MaxRetryError) as single_failure:
        await _probe_media_size(scope, "primary", [])
    with pytest.raises(MaxRetryError) as multiple_failure:
        await _probe_media_size(scope, "primary", ["mirror"])

    assert single_failure.value is failures["primary"]
    assert isinstance(multiple_failure.value.__cause__, ExceptionGroup)
    assert set(multiple_failure.value.__cause__.exceptions) == set(failures.values())


@as_sync
async def test_probe_media_size_rejects_a_source_without_a_known_length(monkeypatch: pytest.MonkeyPatch):
    async def get_size(_scope: ExecutionScope, _url: str) -> Success[None]:
        return Success(None)

    monkeypatch.setattr(Fetcher, "get_size", get_size)
    with pytest.raises(MaxRetryError, match="未返回长度"):
        await _probe_media_size(ExecutionScope(cast("Any", object())), "primary", [])


@as_sync
async def test_native_transfer_failure_uses_the_existing_cli_error_boundary():
    async def fail() -> int:
        raise RuntimeError("all sources exhausted")

    task = asyncio.create_task(fail())
    with pytest.raises(MaxRetryError, match="媒体下载失败：all sources exhausted") as failure:
        await _wait_for_native_transfers([task])

    assert isinstance(failure.value.__cause__, RuntimeError)


@as_sync
async def test_download_files_owns_its_temporary_target():
    payload = b"payload" * 1024

    with LocalRangeServer(payload) as server:
        async with create_client(trust_env=False) as session:
            downloaded = await download_one(ExecutionScope(session), server.url)

    try:
        assert downloaded.parent.name.startswith("yutto-download-")
        assert downloaded.read_bytes() == payload
    finally:
        shutil.rmtree(downloaded.parent, ignore_errors=True)


@as_sync
async def test_out_of_order_ranges_commit_an_exact_temporary_file():
    page_size = 64 * 1024
    payload = b"A" * page_size + b"B" * page_size + b"C" * page_size
    first_range = (0, page_size - 1)
    later_range = (page_size, 2 * page_size - 1)

    with LocalRangeServer(payload, release_after={first_range: later_range}) as server:
        async with create_client(trust_env=False) as session:
            downloaded = await download_one(
                ExecutionScope(session),
                server.url,
                block_size=page_size,
            )

    try:
        assert downloaded.read_bytes() == payload
        completed_ranges = [
            request.range_header for request in server.completed_requests if request.range_header != "bytes=0-1"
        ]
        first_range_header = f"bytes={first_range[0]}-{first_range[1]}"
        later_range_header = f"bytes={later_range[0]}-{later_range[1]}"
        assert completed_ranges.index(later_range_header) < completed_ranges.index(first_range_header)
    finally:
        shutil.rmtree(downloaded.parent, ignore_errors=True)


@as_sync
async def test_cancelling_transfer_cleans_its_temporary_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    page_size = 64 * 1024
    payload = b"A" * page_size + b"B" * page_size + b"C" * page_size + b"D" * page_size
    blocker = (page_size, 2 * page_size - 1)
    later_range = f"bytes={2 * page_size}-{3 * page_size - 1}"
    staging_directory = tmp_path / "transfer-owned"

    def make_staging_directory(**_kwargs: object) -> str:
        staging_directory.mkdir()
        return str(staging_directory)

    monkeypatch.setattr(transfer_module.tempfile, "mkdtemp", make_staging_directory)

    with LocalRangeServer(payload, delays={blocker: 0.2}) as server:
        async with create_client(trust_env=False) as session:
            task = asyncio.create_task(
                download_one(
                    ExecutionScope(session),
                    server.url,
                    block_size=page_size,
                )
            )
            async with asyncio.timeout(2):
                while not any(request.range_header == later_range for request in server.completed_requests):
                    await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await asyncio.sleep(0.25)

    assert not staging_directory.exists()


@as_sync
async def test_download_files_reuses_scope_session_and_maps_workers(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    class WorkerLimit:
        def __init__(self, capacity: int) -> None:
            self.capacity = capacity

    class Snapshot:
        origin_bytes = 0
        received_bytes = 123
        committed_bytes = 123
        window_saturated = False

    class Handle:
        async def wait(self) -> None:
            pass

        def done(self) -> bool:
            return True

        def cancel(self) -> None:
            raise AssertionError("completed handle must not be cancelled")

        def snapshot(self) -> Snapshot:
            return Snapshot()

        def result(self) -> int:
            return 123

    async def get_size(_scope: ExecutionScope, _url: str) -> Success[int]:
        return Success(123)

    class FakeSession:
        def start_transfer(self, *args: object, **kwargs: object) -> Handle:
            captured["args"] = args
            captured["kwargs"] = kwargs
            return Handle()

    monkeypatch.setattr(Fetcher, "get_size", get_size)
    monkeypatch.setattr(transfer_module, "TransferWorkerLimit", WorkerLimit)

    downloaded = await download_one(
        ExecutionScope(cast("Any", FakeSession()), download_workers=3),
        "https://primary.example/media",
        mirrors=("https://blocked.example/media", "https://mirror.example/media"),
        block_size=64 * 1024,
        banned_mirrors_pattern="blocked",
    )
    try:
        args = captured["args"]
        kwargs = captured["kwargs"]
        assert isinstance(args, tuple)
        assert isinstance(kwargs, dict)
        assert args[0] == ["https://primary.example/media", "https://mirror.example/media"]
        assert args[1] == downloaded
        assert args[2] == 123
        assert kwargs["workers"] == 3
        assert kwargs["block_size"] == 64 * 1024
        assert kwargs["overwrite"] is False
        assert isinstance(kwargs["worker_limit"], WorkerLimit)
        assert kwargs["worker_limit"].capacity == 3
    finally:
        shutil.rmtree(downloaded.parent, ignore_errors=True)


@as_sync
async def test_item_transfers_start_together_and_share_one_worker_limit(monkeypatch: pytest.MonkeyPatch):
    started: list[tuple[object, dict[str, object]]] = []
    both_started = asyncio.Event()

    class WorkerLimit:
        def __init__(self, capacity: int) -> None:
            self.capacity = capacity

    class Snapshot:
        origin_bytes = 0
        received_bytes = 1
        committed_bytes = 1
        window_saturated = False

    class Handle:
        async def wait(self) -> None:
            await both_started.wait()

        def done(self) -> bool:
            return both_started.is_set()

        def cancel(self) -> None:
            raise AssertionError("completed handle must not be cancelled")

        def snapshot(self) -> Snapshot:
            return Snapshot()

        def result(self) -> int:
            return 1

    async def get_size(_scope: ExecutionScope, _url: str) -> Success[int]:
        return Success(1)

    class FakeSession:
        def start_transfer(self, *args: object, **kwargs: object) -> Handle:
            started.append((args[0], kwargs))
            if len(started) == 2:
                both_started.set()
            return Handle()

    monkeypatch.setattr(Fetcher, "get_size", get_size)
    monkeypatch.setattr(transfer_module, "TransferWorkerLimit", WorkerLimit)

    downloaded = await download_files(
        ExecutionScope(cast("Any", FakeSession()), download_workers=2),
        (
            ("https://video.example/media", ()),
            ("https://audio.example/media", ()),
        ),
        block_size=64 * 1024,
        banned_mirrors_pattern=None,
    )
    try:
        assert len(started) == 2
        limits = [kwargs["worker_limit"] for _, kwargs in started]
        assert limits[0] is limits[1]
        assert isinstance(limits[0], WorkerLimit)
        assert limits[0].capacity == 2
        assert all(kwargs["workers"] == 2 for _, kwargs in started)
    finally:
        shutil.rmtree(downloaded[0].parent, ignore_errors=True)


@as_sync
async def test_one_worker_preserves_serial_transfer_setup(monkeypatch: pytest.MonkeyPatch):
    started: list[str] = []

    class WorkerLimit:
        def __init__(self, capacity: int) -> None:
            self.capacity = capacity

    class Snapshot:
        origin_bytes = 0
        received_bytes = 1
        committed_bytes = 1
        window_saturated = False

    class Handle:
        def __init__(self, source: str) -> None:
            self.source = source

        async def wait(self) -> None:
            assert started[-1] == self.source

        def done(self) -> bool:
            return True

        def cancel(self) -> None:
            raise AssertionError("completed handle must not be cancelled")

        def snapshot(self) -> Snapshot:
            return Snapshot()

        def result(self) -> int:
            return 1

    async def get_size(_scope: ExecutionScope, _url: str) -> Success[int]:
        return Success(1)

    class FakeSession:
        def start_transfer(self, sources: list[str], *_args: object, **_kwargs: object) -> Handle:
            started.append(sources[0])
            return Handle(sources[0])

    monkeypatch.setattr(Fetcher, "get_size", get_size)
    monkeypatch.setattr(transfer_module, "TransferWorkerLimit", WorkerLimit)

    downloaded = await download_files(
        ExecutionScope(cast("Any", FakeSession()), download_workers=1),
        (("video", ()), ("audio", ())),
        block_size=64 * 1024,
        banned_mirrors_pattern=None,
    )
    try:
        assert started == ["video", "audio"]
    finally:
        shutil.rmtree(downloaded[0].parent, ignore_errors=True)


@as_sync
async def test_rust_backend_reaps_a_started_handle_when_later_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    class Handle:
        def __init__(self) -> None:
            self.cancelled = False
            self.reaped = False

        def done(self) -> bool:
            return self.reaped

        def cancel(self) -> None:
            self.cancelled = True

    handle = Handle()
    starts = 0
    staging_directory = tmp_path / "transfer-owned"

    async def get_size(_scope: ExecutionScope, _url: str) -> Success[int]:
        return Success(123)

    async def wait_for_transfer(started_handle: Handle, **_kwargs: object) -> int:
        while not started_handle.cancelled:
            await asyncio.sleep(0)
        await asyncio.sleep(0)
        started_handle.reaped = True
        raise RuntimeError("cancelled")

    class FakeSession:
        def start_transfer(self, *_args: object, **_kwargs: object) -> Handle:
            nonlocal starts
            starts += 1
            if starts == 2:
                raise RuntimeError("second setup failed")
            return handle

    def make_staging_directory(**_kwargs: object) -> str:
        staging_directory.mkdir()
        return str(staging_directory)

    monkeypatch.setattr(Fetcher, "get_size", get_size)
    monkeypatch.setattr(transfer_module, "wait_for_transfer", wait_for_transfer)
    monkeypatch.setattr(transfer_module.tempfile, "mkdtemp", make_staging_directory)

    with pytest.raises(RuntimeError, match="second setup failed"):
        await download_files(
            ExecutionScope(cast("Any", FakeSession()), download_workers=2),
            (
                ("https://video.example/media", ()),
                ("https://audio.example/media", ()),
            ),
            block_size=64 * 1024,
            banned_mirrors_pattern=None,
        )

    assert handle.cancelled
    assert handle.reaped
    assert not staging_directory.exists()
