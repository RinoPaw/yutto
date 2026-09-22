from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from yutto.core.events import DownloadBatchStarted, DownloadRequestQueued, NullDownloadEventSink
from yutto.core.operation import bind_download_event_sink, emit_download_event
from yutto.scope import MISSING, Scope

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.core.events import DownloadEventSink
    from yutto.core.execution import ExecutionScopeFactory
    from yutto.core.result import DownloadResult, ResolveResult


class DownloadWorkflow(Protocol):
    async def execute(
        self,
        scope_factory: ExecutionScopeFactory,
        scopes: Sequence[Scope],
    ) -> DownloadResult: ...


class ResolveWorkflow(Protocol):
    async def execute_resolve(
        self,
        scope_factory: ExecutionScopeFactory,
        scopes: Sequence[Scope],
    ) -> ResolveResult: ...


class YuttoApplication:
    """Frontend-independent orchestration for one yutto invocation."""

    def __init__(
        self,
        scope_factory: ExecutionScopeFactory,
        *,
        workflow: DownloadWorkflow,
        event_sink: DownloadEventSink | None = None,
        resolve_workflow: ResolveWorkflow | None = None,
    ):
        self.scope_factory = scope_factory
        self.workflow = workflow
        self.resolve_workflow = resolve_workflow
        self.event_sink = event_sink if event_sink is not None else NullDownloadEventSink()

    async def download_all(self, scopes: Sequence[Scope]) -> DownloadResult:
        with bind_download_event_sink(self.event_sink):
            total = len(scopes)
            if total > 1:
                emit_download_event(DownloadBatchStarted(total=total))
                for index, scope in enumerate(scopes, start=1):
                    source = scope.source.value
                    emit_download_event(
                        DownloadRequestQueued(
                            url="" if source is MISSING or source is None else str(source),
                            index=index,
                            total=total,
                        )
                    )
            return await self.workflow.execute(self.scope_factory, scopes)

    async def download(self, scope: Scope) -> DownloadResult:
        return await self.download_all([scope])

    async def resolve_all(self, scopes: Sequence[Scope]) -> ResolveResult:
        if self.resolve_workflow is None:
            raise RuntimeError("this application was built without a resolve workflow")
        with bind_download_event_sink(self.event_sink):
            return await self.resolve_workflow.execute_resolve(self.scope_factory, scopes)

    async def resolve(self, scope: Scope) -> ResolveResult:
        return await self.resolve_all([scope])
