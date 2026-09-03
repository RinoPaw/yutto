from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from yutto.core.operation import ReportLevel, emit_download_report
from yutto.exceptions import NoAccessPermissionError, NotFoundError, WrongArgumentError
from yutto.types import BilibiliId, Options
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.metadata import Actor

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.media import MediaContainer


@dataclass(slots=True, kw_only=True)
class SourceOptions(Options):
    selections: tuple[int, ...] = ()
    with_extra_episodes: bool = False
    skip_preview: bool = False
    require_metadata: bool = False


@dataclass(slots=True, kw_only=True)
class Source(ABC):
    id: BilibiliId
    selections: tuple[int, ...] = ()
    options: SourceOptions = field(default_factory=SourceOptions)

    def __init__(self, id: BilibiliId, page: int = 1, options: SourceOptions | None = None):
        self.options = options or SourceOptions()
        self.id = id
        self.selections = self.options.selections or (page,)

    @abstractmethod
    async def resolve(self, scope: ExecutionScope) -> MediaContainer:
        raise NotImplementedError

    @staticmethod
    def _parse_actors_info(video_info: dict[str, Any]) -> list[Actor]:
        if staff := video_info.get("staff"):
            return [
                Actor(
                    name=staff_info["name"],
                    role=staff_info["title"],
                    thumb=staff_info["face"],
                    profile=f"https://space.bilibili.com/{staff_info['mid']}",
                    order=index,
                )
                for index, staff_info in enumerate(staff)
            ]

        if owner := video_info.get("owner"):
            return [
                Actor(
                    name=owner["name"],
                    role="UP主",
                    thumb=owner["face"],
                    profile=f"https://space.bilibili.com/{owner['mid']}",
                    order=0,
                )
            ]

        emit_download_report("未找到演职人员信息", ReportLevel.WARNING)
        return []

    @staticmethod
    def _parse_genre_info(video_info: dict[str, Any]) -> list[str]:
        genre = video_info.get("tname")
        return [genre] if isinstance(genre, str) and genre else []

    @staticmethod
    async def _fetch_payload(
        scope: ExecutionScope,
        url: str,
        description: str,
        identifier: str,
        data_key: str,
    ) -> dict[str, Any]:
        response = unwrap_fetch_result(await Fetcher.fetch_json(scope, url))
        if response.get("code") == -404:
            raise NotFoundError(f"未找到{description}（{identifier}）")
        payload = response.get(data_key)
        if payload is None:
            raise NoAccessPermissionError(f"无法解析{description}（{identifier}），原因：{response.get('message')}")
        return payload


@dataclass(slots=True, kw_only=True)
class AmbiguousSource(Source):
    candidates: tuple[Source, ...]

    async def resolve(self, scope: ExecutionScope) -> MediaContainer:
        results = await asyncio.gather(
            *(candidate.resolve(scope) for candidate in self.candidates),
            return_exceptions=True,
        )
        successes = [result for result in results if not isinstance(result, BaseException)]
        if len(successes) > 1:
            raise WrongArgumentError("该 ID 同时存在于多个命名空间，无法自动判断")
        if successes:
            return successes[0]

        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, NotFoundError):
                raise result
        raise NotFoundError("未找到对应的内容")
