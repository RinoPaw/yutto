from __future__ import annotations

from typing import Any, cast

import pytest

from yutto.config import ResolvedConfig, SourceSpec
from yutto.core.execution import ExecutionScope, RequestExecutionScopeFactory
from yutto.utils.functional import as_sync

pytestmark = pytest.mark.processor


def make_config() -> ResolvedConfig:
    return ResolvedConfig(source=SourceSpec(value="BV1scope"))


@pytest.mark.parametrize(
    ("fetch_workers", "download_workers", "field"),
    [
        (0, 8, "fetch_workers"),
        (8, 0, "download_workers"),
    ],
)
def test_execution_scope_rejects_non_positive_workers(
    fetch_workers: int,
    download_workers: int,
    field: str,
):
    with pytest.raises(ValueError, match=rf"{field} must be at least 1"):
        ExecutionScope(
            cast("Any", object()),
            fetch_workers=fetch_workers,
            download_workers=download_workers,
        )


@as_sync
async def test_scope_factory_opens_fresh_sessions_limiters_and_caches():
    factory = RequestExecutionScopeFactory()
    config = make_config()

    async with factory.open(config) as first_scope:
        first_session = first_scope.session
        first_fetch_limiter = first_scope.fetch_limiter
        assert first_scope.download_workers == 8
        first_scope.nav_cache = {"data": {"isLogin": True}}
        first_scope.touched_urls.add("https://example.com")

    assert first_session.is_closed

    async with factory.open(config) as second_scope:
        assert second_scope.session is not first_session
        assert second_scope.fetch_limiter is not first_fetch_limiter
        assert second_scope.download_workers == 8
        assert second_scope.nav_cache is None
        assert second_scope.touched_urls == set()


@as_sync
async def test_scope_factory_closes_session_when_on_open_fails():
    sessions: list[Any] = []

    async def fail_on_open(execution: ExecutionScope, config: ResolvedConfig) -> None:
        sessions.append(execution.session)
        raise RuntimeError("on_open failed")

    factory = RequestExecutionScopeFactory(on_open=fail_on_open)

    with pytest.raises(RuntimeError, match="on_open failed"):
        async with factory.open(make_config()):
            pytest.fail("scope should not be yielded")

    assert len(sessions) == 1
    assert sessions[0].is_closed
