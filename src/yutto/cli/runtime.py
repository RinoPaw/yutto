from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from yutto.cli.settings import YuttoConfig


@dataclass(frozen=True, slots=True)
class RuntimeOptions:
    """Process-level options for one CLI/server invocation."""

    jobs: int
    ffmpeg_path: str | None
    preview_formats: bool
    no_color: bool
    no_progress: bool
    debug: bool


def resolve_runtime_options(values: Mapping[str, object], settings: YuttoConfig) -> RuntimeOptions:
    """Resolve CLI overrides over persistent process-level settings."""
    jobs_value = values.get("jobs", settings.basic.jobs if settings.basic.jobs is not None else 1)
    if type(jobs_value) is not int or jobs_value < 1:
        raise ValueError(f"jobs 参数值（{jobs_value}）不满足要求哦（应为不小于 1 的整数）")

    ffmpeg_path = values.get("ffmpeg_path", settings.basic.ffmpeg_path)
    if ffmpeg_path is not None and not isinstance(ffmpeg_path, str):
        raise TypeError("ffmpeg_path must be a string or null")

    return RuntimeOptions(
        jobs=jobs_value,
        ffmpeg_path=ffmpeg_path,
        preview_formats=_resolve_bool(values, "preview_formats"),
        no_color=_resolve_bool(values, "no_color", settings.basic.no_color),
        no_progress=_resolve_bool(values, "no_progress", settings.basic.no_progress),
        debug=_resolve_bool(values, "debug", settings.basic.debug),
    )


def _resolve_bool(
    values: Mapping[str, object],
    name: str,
    configured: bool | None = None,
) -> bool:
    value = values.get(name, False if configured is None else configured)
    if type(value) is not bool:
        raise TypeError(f"{name} must be a boolean")
    return value
