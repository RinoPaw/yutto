from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.cli.settings import scope_from_config
from yutto.scope import Scope

if TYPE_CHECKING:
    from yutto.cli.settings import YuttoConfig


@dataclass(frozen=True)
class RuntimeOptions:
    """CLI process options after applying the active scope chain."""

    jobs: int
    ffmpeg_path: str | None
    preview_formats: bool
    no_color: bool
    no_progress: bool
    debug: bool


def resolve_runtime_options(
    scope: Scope | dict[str, Any],
    config: YuttoConfig | None = None,
) -> RuntimeOptions:
    if not isinstance(scope, Scope):
        if config is None:
            raise TypeError("config is required when resolving a raw value mapping")
        scope = Scope(scope, parent=scope_from_config(config))

    jobs = scope.runtime.jobs
    try:
        resolved_jobs = int(jobs)
        if resolved_jobs < 1:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）") from None

    ffmpeg_path = scope.runtime.ffmpeg_path

    return RuntimeOptions(
        jobs=resolved_jobs,
        ffmpeg_path=None if ffmpeg_path is None else str(ffmpeg_path),
        preview_formats=bool(scope.runtime.preview_formats),
        no_color=bool(scope.runtime.no_color),
        no_progress=bool(scope.runtime.no_progress),
        debug=bool(scope.runtime.debug),
    )
