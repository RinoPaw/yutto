from __future__ import annotations

from pathlib import Path

import pytest

from yutto.core.execution import RequestExecutionScopeFactory
from yutto.core.result import DownloadResult
from yutto.core.task_service import DownloadTaskService
from yutto.runtime import TaskState
from yutto.scope import ROOT_SCOPE, Scope
from yutto.utils.functional import as_sync

pytestmark = pytest.mark.processor


@as_sync
async def test_download_task_service_executes_private_scope_and_exposes_request_scope() -> None:
    request_scope = Scope(
        {
            "source.value": "BV1scope",
            "output.directory": Path("shows/season-1"),
        },
        parent=ROOT_SCOPE,
    )
    execution_scope = Scope(
        {"output.directory": Path("/server/downloads/shows/season-1")},
        parent=request_scope,
    )
    executed: list[Scope] = []

    class RecordingApplication:
        async def download(self, scope: Scope) -> DownloadResult:
            executed.append(scope)
            return DownloadResult()

    service = DownloadTaskService(
        RequestExecutionScopeFactory(),
        application_factory=lambda factory, event_sink: RecordingApplication(),
    )
    async with service:
        submitted = await service.submit(request_scope, execution_scope=execution_scope)
        completed = await service.runtime.wait(submitted.task_id)

        assert completed is not None and completed.state is TaskState.COMPLETED
        public = service.get(submitted.task_id)
        assert public is not None
        assert public.payload is request_scope
        assert public.payload.output.directory == Path("shows/season-1")
        assert executed == [execution_scope]
        assert executed[0].output.directory == Path("/server/downloads/shows/season-1")
