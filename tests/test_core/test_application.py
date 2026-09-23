from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from yutto.core.application import YuttoApplication
from yutto.core.events import DownloadBatchStarted, DownloadRequestQueued, DownloadStage, DownloadStageChanged
from yutto.core.execution import ExecutionScopeFactory, RequestExecutionScopeFactory
from yutto.core.operation import emit_download_event
from yutto.core.result import DownloadResult, ResolveResult
from yutto.scope import ROOT_SCOPE, Scope
from yutto.utils.functional import as_sync

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.core.events import DownloadEvent

pytestmark = pytest.mark.processor


class RecordingEventSink:
    def __init__(self, trace: list[tuple[str, object]]):
        self.events: list[DownloadEvent] = []
        self.trace = trace

    def emit(self, event: DownloadEvent) -> None:
        self.events.append(event)
        self.trace.append(("event", event))


class RecordingWorkflow:
    def __init__(self, trace: list[tuple[str, object]]):
        self.trace = trace
        self.result = DownloadResult()

    async def execute(
        self,
        scope_factory: ExecutionScopeFactory,
        scopes: Sequence[Scope],
    ) -> DownloadResult:
        self.trace.append(("execute", (scope_factory, tuple(scopes))))
        emit_download_event(DownloadStageChanged(name=DownloadStage.RESOLVING))
        return self.result


class RecordingResolveWorkflow:
    def __init__(self, trace: list[tuple[str, object]]):
        self.trace = trace
        self.result = ResolveResult()

    async def execute_resolve(
        self,
        scope_factory: ExecutionScopeFactory,
        scopes: Sequence[Scope],
    ) -> ResolveResult:
        self.trace.append(("execute_resolve", (scope_factory, tuple(scopes))))
        emit_download_event(DownloadStageChanged(name=DownloadStage.RESOLVING))
        return self.result


def make_scope(url: str) -> Scope:
    return Scope({"source.value": url}, parent=ROOT_SCOPE)


@as_sync
async def test_application_preserves_queue_order_and_emits_batch_events():
    scope_factory = RequestExecutionScopeFactory()
    trace: list[tuple[str, object]] = []
    workflow = RecordingWorkflow(trace)
    sink = RecordingEventSink(trace)
    scopes = [make_scope("BV1first"), make_scope("BV1second")]

    application = YuttoApplication(scope_factory, workflow=workflow, event_sink=sink)
    result = await application.download_all(scopes)

    assert trace == [
        ("event", DownloadBatchStarted(total=2)),
        ("event", DownloadRequestQueued(url="BV1first", index=1, total=2)),
        ("event", DownloadRequestQueued(url="BV1second", index=2, total=2)),
        ("execute", (scope_factory, tuple(scopes))),
        ("event", DownloadStageChanged(name=DownloadStage.RESOLVING)),
    ]
    assert sink.events == [
        DownloadBatchStarted(total=2),
        DownloadRequestQueued(url="BV1first", index=1, total=2),
        DownloadRequestQueued(url="BV1second", index=2, total=2),
        DownloadStageChanged(name=DownloadStage.RESOLVING),
    ]
    assert result is workflow.result


@as_sync
async def test_single_download_does_not_emit_batch_presentation_events():
    trace: list[tuple[str, object]] = []
    workflow = RecordingWorkflow(trace)
    sink = RecordingEventSink(trace)
    scope_factory = RequestExecutionScopeFactory()
    scope = make_scope("BV1single")
    application = YuttoApplication(
        scope_factory,
        workflow=workflow,
        event_sink=sink,
    )

    result = await application.download(scope)

    assert sink.events == [DownloadStageChanged(name=DownloadStage.RESOLVING)]
    assert trace == [
        ("execute", (scope_factory, (scope,))),
        ("event", DownloadStageChanged(name=DownloadStage.RESOLVING)),
    ]
    assert result is workflow.result


@as_sync
async def test_application_resolve_uses_resolve_workflow_and_event_sink():
    scope_factory = RequestExecutionScopeFactory()
    trace: list[tuple[str, object]] = []
    workflow = RecordingWorkflow(trace)
    resolve_workflow = RecordingResolveWorkflow(trace)
    sink = RecordingEventSink(trace)
    scope = make_scope("BV1resolve")
    application = YuttoApplication(
        scope_factory,
        workflow=workflow,
        event_sink=sink,
        resolve_workflow=resolve_workflow,
    )

    result = await application.resolve(scope)

    assert result is resolve_workflow.result
    assert trace == [
        ("execute_resolve", (scope_factory, (scope,))),
        ("event", DownloadStageChanged(name=DownloadStage.RESOLVING)),
    ]


@as_sync
async def test_application_resolve_requires_resolve_workflow():
    application = YuttoApplication(RequestExecutionScopeFactory(), workflow=RecordingWorkflow([]))

    with pytest.raises(RuntimeError, match="resolve workflow"):
        await application.resolve(make_scope("BV1resolve"))
