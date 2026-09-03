from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from yutto.exceptions import WrongArgumentError
from yutto.types import ResolvableEpisode

if TYPE_CHECKING:
    from typing import TypeAlias

    from yutto.exceptions import YuttoBaseException
    from yutto.extractor.outcome import ResolveOutcome
    from yutto.source import Source, SourceOptions

    ExtractorResolveOutcome: TypeAlias = ResolveOutcome[ResolvableEpisode, YuttoBaseException]

EpisodeListedCallback = Callable[[ResolvableEpisode], Awaitable[None]]


class Parser(ABC):
    @abstractmethod
    def parse(self, url: str, options: SourceOptions) -> Source | None:
        raise NotImplementedError

    @staticmethod
    def _single_query_value(query: dict[str, list[str]], key: str) -> str | None:
        values = query.get(key)
        if values is None:
            return None
        if len(values) != 1:
            raise WrongArgumentError(f"参数 {key} 重复出现（值: {values}）")
        return values[0]
