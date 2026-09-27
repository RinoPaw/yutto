from __future__ import annotations

from pathlib import Path

import pytest

from yutto.config import OutputSpec, ResolvedConfig, SourceSpec
from yutto.core.execution import RequestExecutionScopeFactory
from yutto.core.result import DownloadResult
from yutto.core.task_service import DownloadTaskService
from yutto.runtime import TaskState
from yutto.utils.functional import as_sync

pytestmark = pytest.mark.processor


@as_sync
async def test_download_task_service_executes_private_config_and_exposes_request_config() -> None:
    request_config = ResolvedConfig(
        source=SourceSpec(value="BV1scope"),
        output=OutputSpec(directory=Path("shows/season-1")),
    )
    execution_config = ResolvedConfig(
        source=request_config.source,
        selection=request_config.selection,
        credential=request_config.credential,
        access=request_config.access,
        resource=request_config.resource,
        stream=request_config.stream,
        output=OutputSpec(directory=Path("/server/downloads/shows/season-1")),
        network=request_config.network,
        danmaku=request_config.danmaku,
    )
    executed: list[ResolvedConfig] = []

    class RecordingApplication:
        async def download(self, config: ResolvedConfig) -> DownloadResult:
            executed.append(config)
            return DownloadResult()

    service = DownloadTaskService(
        RequestExecutionScopeFactory(),
        application_factory=lambda factory, event_sink: RecordingApplication(),
    )
    async with service:
        submitted = await service.submit(request_config, execution_config=execution_config)
        completed = await service.runtime.wait(submitted.task_id)

        assert completed is not None and completed.state is TaskState.COMPLETED
        public = service.get(submitted.task_id)
        assert public is not None
        assert public.payload is request_config
        assert public.payload.output.directory == Path("shows/season-1")
        assert executed == [execution_config]
        assert executed[0].output.directory == Path("/server/downloads/shows/season-1")
