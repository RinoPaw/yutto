from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.cli.scope import MISSING, Scope
from yutto.cli.settings import scope_from_config

if TYPE_CHECKING:
    from yutto.cli.settings import YuttoConfig


@dataclass(frozen=True)
class RuntimeOptions:
    """CLI process options after applying the active scope chain."""

    jobs: int | None
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

    jobs = scope.lookup("jobs")
    if jobs is MISSING:
        resolved_jobs = None
    else:
        try:
            resolved_jobs = int(jobs)
            if resolved_jobs < 1:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）") from None

    ffmpeg_path = scope.lookup("ffmpeg_path")

    return RuntimeOptions(
        jobs=resolved_jobs,
        ffmpeg_path=None if ffmpeg_path is MISSING or ffmpeg_path is None else str(ffmpeg_path),
        preview_formats=_bool_value(scope, "preview_formats"),
        no_color=_bool_value(scope, "no_color"),
        no_progress=_bool_value(scope, "no_progress"),
        debug=_bool_value(scope, "debug"),
    )


def _bool_value(scope: Scope, key: str) -> bool:
    value = scope.lookup(key)
    return False if value is MISSING else bool(value)
