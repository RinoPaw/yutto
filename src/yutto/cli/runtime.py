from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.cli.settings import resolved_config_from_settings
from yutto.scope import ResolvedConfig, merge_configs

if TYPE_CHECKING:
    from yutto.cli.settings import YuttoConfig


@dataclass(frozen=True)
class RuntimeOptions:
    """CLI process options read from one flat resolved config."""

    jobs: int
    ffmpeg_path: str | None
    preview_formats: bool
    no_color: bool
    no_progress: bool
    debug: bool


def resolve_runtime_options(
    config: ResolvedConfig | dict[str, Any],
    settings: YuttoConfig | None = None,
) -> RuntimeOptions:
    if not isinstance(config, ResolvedConfig):
        if settings is None:
            raise TypeError("settings is required when resolving a raw value mapping")
        config = merge_configs(resolved_config_from_settings(settings), ResolvedConfig(config))

    jobs = config.runtime.jobs
    try:
        resolved_jobs = int(jobs)
        if resolved_jobs < 1:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）") from None

    ffmpeg_path = config.runtime.ffmpeg_path

    return RuntimeOptions(
        jobs=resolved_jobs,
        ffmpeg_path=None if ffmpeg_path is None else str(ffmpeg_path),
        preview_formats=bool(config.runtime.preview_formats),
        no_color=bool(config.runtime.no_color),
        no_progress=bool(config.runtime.no_progress),
        debug=bool(config.runtime.debug),
    )
