from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from yutto.media import Media


class _ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactKind(StrEnum):
    MEDIA = "media"
    SUBTITLE = "subtitle"
    DANMAKU = "danmaku"
    METADATA = "metadata"
    COVER = "cover"


class ItemState(StrEnum):
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class ItemSkipReason(StrEnum):
    ALREADY_EXISTS = "already_exists"
    NO_MEDIA_STREAM = "no_media_stream"


class Artifact(_ResultModel):
    kind: ArtifactKind
    path: Path


class ItemFailure(_ResultModel):
    type: str
    message: str
    code: int | str


class ItemResult(_ResultModel):
    # Filled by DownloadManager once the item has crossed the path-planning boundary.
    # Executor-local results may omit it while they are still inside that operation.
    planned_path: Path | None = None
    state: ItemState
    output_path: Path | None = None
    skip_reason: ItemSkipReason | None = None
    failure: ItemFailure | None = None
    artifacts: tuple[Artifact, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state is ItemState.DONE:
            if self.skip_reason is not None:
                raise ValueError("done item must not have a skip reason")
            if self.failure is not None:
                raise ValueError("done item must not have a failure")
        elif self.state is ItemState.SKIPPED:
            if self.skip_reason is None:
                raise ValueError("skipped item must have a skip reason")
            if self.failure is not None:
                raise ValueError("skipped item must not have a failure")
            if self.skip_reason is ItemSkipReason.ALREADY_EXISTS and self.output_path is None:
                raise ValueError("already-existing item must have an output path")
            if self.skip_reason is ItemSkipReason.NO_MEDIA_STREAM and self.output_path is not None:
                raise ValueError("item without a media stream must not have an output path")
        elif self.state is ItemState.FAILED:
            if self.output_path is not None:
                raise ValueError("failed item must not have an output path")
            if self.skip_reason is not None:
                raise ValueError("failed item must not have a skip reason")
            if self.failure is None:
                raise ValueError("failed item must have a failure")
        return self

    @property
    def has_downloaded_media(self) -> bool:
        return self.state is ItemState.DONE and any(artifact.kind is ArtifactKind.MEDIA for artifact in self.artifacts)


class DownloadResult(_ResultModel):
    items: tuple[ItemResult, ...] = Field(default_factory=tuple)


class ResolveFailureStep(_ResultModel):
    index: int
    source: str


class ResolveFailure(_ResultModel):
    """一次预期内的解析失败（视频不存在 / 无访问权限 / 请求重试耗尽等）。

    ``path`` 保留从外层容器到失败 source 的解析路径；``type`` / ``message`` /
    ``code`` 与任务级错误（TaskError）同构，``code`` 来自 yutto 的稳定错误码表。
    """

    path: tuple[ResolveFailureStep, ...] = Field(default_factory=tuple)
    type: str
    message: str
    code: int | str


@dataclass(frozen=True, slots=True)
class ResolveResult:
    """Resolve 结果直接保留每个请求得到的 Media 根节点。"""

    items: tuple[Media, ...] = ()
    failures: tuple[ResolveFailure, ...] = ()
