from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Self, TypeVar, assert_never

from yutto.core.events import (
    DownloadArtifactCreated,
    DownloadBatchStarted,
    DownloadEvent,
    DownloadEventSink,
    DownloadItemSkipped,
    DownloadMediaSelected,
    DownloadProgress,
    DownloadRequestQueued,
    DownloadStageChanged,
)
from yutto.core.result import DownloadResult, ResolveResult
from yutto.runtime import TaskRuntime, TaskSnapshot
from yutto.scope import Scope

if TYPE_CHECKING:
    from collections.abc import Callable

    from yutto.core.execution import ExecutionScopeFactory
    from yutto.runtime import EventReplay, TaskCapacityPool, TaskContext, TaskEvent


_ResultT = TypeVar("_ResultT")


@dataclass(frozen=True, slots=True)
class _TaskScope:
    """Keep the submitted request Scope separate from the Scope used for execution."""

    request: Scope
    execution: Scope


def _public_snapshot(snapshot: TaskSnapshot[_TaskScope, _ResultT]) -> TaskSnapshot[Scope, _ResultT]:
    return TaskSnapshot(
        task_id=snapshot.task_id,
        state=snapshot.state,
        payload=snapshot.payload.request,
        result=snapshot.result,
        error=snapshot.error,
        created_at=snapshot.created_at,
        started_at=snapshot.started_at,
        finished_at=snapshot.finished_at,
        last_event_seq=snapshot.last_event_seq,
    )


class DownloadApplication(Protocol):
    async def download(self, scope: Scope) -> DownloadResult: ...


class ResolveApplication(Protocol):
    async def resolve(self, scope: Scope) -> ResolveResult: ...


class DownloadTaskService:
    """Run frontend-independent download scopes through a bounded worker runtime."""

    def __init__(
        self,
        scope_factory: ExecutionScopeFactory,
        application_factory: Callable[[ExecutionScopeFactory, DownloadEventSink], DownloadApplication],
        *,
        replay_limit: int = 100,
        task_limit: int = 256,
        worker_count: int = 1,
        task_id_factory: Callable[[], str] | None = None,
        seq_allocator: Callable[[], int] | None = None,
        capacity_pool: TaskCapacityPool | None = None,
    ):
        self._scope_factory = scope_factory
        self._application_factory = application_factory
        self.runtime = TaskRuntime[_TaskScope, DownloadResult](
            self._run,
            worker_count=worker_count,
            replay_limit=replay_limit,
            task_limit=task_limit,
            task_id_factory=task_id_factory,
            seq_allocator=seq_allocator,
            capacity_pool=capacity_pool,
        )

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close(cancel_pending=True)

    async def start(self) -> None:
        await self.runtime.start()

    async def close(self, *, cancel_pending: bool = False) -> None:
        await self.runtime.close(cancel_pending=cancel_pending)

    async def submit(
        self,
        scope: Scope,
        *,
        execution_scope: Scope | None = None,
    ) -> TaskSnapshot[Scope, DownloadResult]:
        task_scope = _TaskScope(
            request=scope,
            execution=scope if execution_scope is None else execution_scope,
        )
        return _public_snapshot(await self.runtime.submit(task_scope))

    def get(self, task_id: str) -> TaskSnapshot[Scope, DownloadResult] | None:
        snapshot = self.runtime.get(task_id)
        return None if snapshot is None else _public_snapshot(snapshot)

    def list(self) -> tuple[TaskSnapshot[Scope, DownloadResult], ...]:
        return tuple(_public_snapshot(snapshot) for snapshot in self.runtime.list())

    async def cancel(self, task_id: str) -> TaskSnapshot[Scope, DownloadResult] | None:
        snapshot = await self.runtime.cancel(task_id)
        return None if snapshot is None else _public_snapshot(snapshot)

    def replay(self, task_id: str, *, after_seq: int = 0) -> EventReplay | None:
        return self.runtime.replay(task_id, after_seq=after_seq)

    def add_event_listener(self, listener: Callable[[TaskEvent], None]) -> Callable[[], None]:
        return self.runtime.add_event_listener(listener)

    async def _run(self, task_scope: _TaskScope, task_context: TaskContext) -> DownloadResult:
        application = self._application_factory(self._scope_factory, _RuntimeDownloadEventSink(task_context))
        return await application.download(task_scope.execution)


class ResolveTaskService:
    """Run frontend-independent resolve scopes through a single-worker runtime.

    Resolve tasks run in their own runtime so that enumerating a collection is
    never queued behind a long-running download task.
    """

    def __init__(
        self,
        scope_factory: ExecutionScopeFactory,
        application_factory: Callable[[ExecutionScopeFactory, DownloadEventSink], ResolveApplication],
        *,
        replay_limit: int = 100,
        task_limit: int = 256,
        task_id_factory: Callable[[], str] | None = None,
        seq_allocator: Callable[[], int] | None = None,
        capacity_pool: TaskCapacityPool | None = None,
    ):
        self._scope_factory = scope_factory
        self._application_factory = application_factory
        self.runtime = TaskRuntime[_TaskScope, ResolveResult](
            self._run,
            worker_count=1,
            replay_limit=replay_limit,
            task_limit=task_limit,
            task_id_factory=task_id_factory,
            seq_allocator=seq_allocator,
            capacity_pool=capacity_pool,
        )

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close(cancel_pending=True)

    async def start(self) -> None:
        await self.runtime.start()

    async def close(self, *, cancel_pending: bool = False) -> None:
        await self.runtime.close(cancel_pending=cancel_pending)

    async def submit(
        self,
        scope: Scope,
        *,
        execution_scope: Scope | None = None,
    ) -> TaskSnapshot[Scope, ResolveResult]:
        task_scope = _TaskScope(
            request=scope,
            execution=scope if execution_scope is None else execution_scope,
        )
        return _public_snapshot(await self.runtime.submit(task_scope))

    def get(self, task_id: str) -> TaskSnapshot[Scope, ResolveResult] | None:
        snapshot = self.runtime.get(task_id)
        return None if snapshot is None else _public_snapshot(snapshot)

    def list(self) -> tuple[TaskSnapshot[Scope, ResolveResult], ...]:
        return tuple(_public_snapshot(snapshot) for snapshot in self.runtime.list())

    async def cancel(self, task_id: str) -> TaskSnapshot[Scope, ResolveResult] | None:
        snapshot = await self.runtime.cancel(task_id)
        return None if snapshot is None else _public_snapshot(snapshot)

    def replay(self, task_id: str, *, after_seq: int = 0) -> EventReplay | None:
        return self.runtime.replay(task_id, after_seq=after_seq)

    def add_event_listener(self, listener: Callable[[TaskEvent], None]) -> Callable[[], None]:
        return self.runtime.add_event_listener(listener)

    async def _run(self, task_scope: _TaskScope, task_context: TaskContext) -> ResolveResult:
        application = self._application_factory(self._scope_factory, _RuntimeDownloadEventSink(task_context))
        return await application.resolve(task_scope.execution)


class _RuntimeDownloadEventSink:
    def __init__(self, task_context: TaskContext):
        self._task_context = task_context

    def emit(self, event: DownloadEvent) -> None:
        kind, data = _encode_runtime_event(event)
        self._task_context.emit(kind, data)


def _encode_runtime_event(event: DownloadEvent) -> tuple[str, dict[str, object]]:
    match event:
        case DownloadBatchStarted(total=total):
            return "batch_started", {"total": total}
        case DownloadRequestQueued(url=url, index=index, total=total):
            return "request_queued", {"url": url, "index": index, "total": total}
        case DownloadStageChanged(name=name, item=item):
            data: dict[str, object] = {"name": name.value}
            if item is not None:
                data["item"] = item
            return "stage", data
        case DownloadProgress(
            current=current,
            total=total,
            speed_per_second=speed,
            phase=phase,
            unit=unit,
            item=item,
        ):
            data: dict[str, object] = {
                "phase": phase.value,
                "current": current,
                "total": total,
                "speed_per_second": speed,
                "unit": unit,
            }
            if item is not None:
                data["item"] = item
            return "progress", data
        case DownloadMediaSelected(item=item, video=video, audio=audio):
            return "media_selected", {
                "item": item,
                "video": (
                    {
                        "codec": video.codec,
                        "quality": video.quality,
                        "width": video.width,
                        "height": video.height,
                        "save_codec": video.save_codec,
                    }
                    if video is not None
                    else None
                ),
                "audio": (
                    {
                        "codec": audio.codec,
                        "quality": audio.quality,
                        "save_codec": audio.save_codec,
                    }
                    if audio is not None
                    else None
                ),
            }
        case DownloadItemSkipped(item=item, reason=reason):
            return "item_skipped", {"item": item, "reason": reason.value}
        case DownloadArtifactCreated(item=item, path=path):
            return "artifact_created", {"path": path.as_posix(), "item": item}
        case _ as unreachable:
            assert_never(unreachable)
