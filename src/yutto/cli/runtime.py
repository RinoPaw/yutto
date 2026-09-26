from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from yutto.cli.settings import resolved_config_from_settings
from yutto.config import ResolvedConfig

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
        config = resolved_config_from_settings(settings).with_overrides(config)

    jobs = config.runtime.jobs
    if jobs < 1:
        raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）")

    return RuntimeOptions(
        jobs=jobs,
        ffmpeg_path=config.runtime.ffmpeg_path,
        preview_formats=config.runtime.preview_formats,
        no_color=config.runtime.no_color,
        no_progress=config.runtime.no_progress,
        debug=config.runtime.debug,
    )
