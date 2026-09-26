from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Protocol

from yutto.utils.fetcher import cookies_from_auth, create_client, resolve_proxy

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable
    from contextlib import AbstractAsyncContextManager

    from yutto._native import YuttoSession
    from yutto.auth import AuthInfo
    from yutto.scope import ResolvedConfig


class ExecutionScope:
    """Runtime resources owned by one resolved configuration execution."""

    session: YuttoSession
    fetch_limiter: asyncio.Semaphore
    download_workers: int
    nav_cache: dict[str, Any] | None
    nav_lock: asyncio.Lock
    touched_urls: set[str]
    enforce_output_boundary: bool

    def __init__(
        self,
        session: YuttoSession,
        *,
        fetch_workers: int,
        download_workers: int,
        enforce_output_boundary: bool = False,
    ):
        if fetch_workers < 1:
            raise ValueError("fetch_workers must be at least 1")
        if download_workers < 1:
            raise ValueError("download_workers must be at least 1")
        self.session = session
        self.fetch_limiter = asyncio.Semaphore(fetch_workers)
        self.download_workers = download_workers
        self.nav_cache = None
        self.nav_lock = asyncio.Lock()
        self.touched_urls = set()
        self.enforce_output_boundary = enforce_output_boundary

    @asynccontextmanager
    async def fetch_guard(self):
        async with self.fetch_limiter:
            yield


def resolve_network_proxy(config: ResolvedConfig) -> str:
    value = config.network.proxy
    if not isinstance(value, str):
        raise ValueError("proxy must be a string")
    return value


def resolve_fetch_workers(config: ResolvedConfig) -> int:
    return _resolve_worker_count(config.network.fetch_workers, "fetch_workers")


def resolve_download_workers(config: ResolvedConfig) -> int:
    return _resolve_worker_count(config.network.download_workers, "download_workers")


def _resolve_worker_count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


class ExecutionScopeFactory(Protocol):
    """Open runtime resources required by one resolved configuration."""

    def open(self, config: ResolvedConfig) -> AbstractAsyncContextManager[ExecutionScope]: ...


class RequestExecutionScopeFactory:
    """Build task-scoped clients, concurrency guards, credentials, and caches."""

    def __init__(
        self,
        credential_resolver: Callable[[ResolvedConfig], AuthInfo | None] | None = None,
        *,
        on_open: Callable[[ExecutionScope, ResolvedConfig], Awaitable[None]] | None = None,
        enforce_output_boundary: bool = False,
    ):
        self._credential_resolver = credential_resolver or (lambda config: None)
        self._on_open = on_open
        self._enforce_output_boundary = enforce_output_boundary

    @asynccontextmanager
    async def open(self, config: ResolvedConfig) -> AsyncIterator[ExecutionScope]:
        proxy, trust_env = resolve_proxy(resolve_network_proxy(config))
        auth = self._credential_resolver(config)
        cookies = cookies_from_auth(auth)

        async with create_client(
            cookies=cookies,
            trust_env=trust_env,
            proxy=proxy,
        ) as session:
            execution = ExecutionScope(
                session,
                fetch_workers=resolve_fetch_workers(config),
                download_workers=resolve_download_workers(config),
                enforce_output_boundary=self._enforce_output_boundary,
            )
            if self._on_open is not None:
                await self._on_open(execution, config)
            yield execution
