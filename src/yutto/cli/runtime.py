from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from yutto.cli.settings import YuttoConfig


@dataclass(frozen=True)
class RuntimeOptions:
    """CLI process options after applying persistent configuration overrides.

    ``None`` means the CLI did not override a default owned by a lower layer.
    """

    jobs: int | None
    ffmpeg_path: str | None
    preview_formats: bool
    no_color: bool
    no_progress: bool
    debug: bool


def resolve_runtime_options(
    values: dict[str, Any],
    config: YuttoConfig,
) -> RuntimeOptions:
    jobs = values.get("jobs", config.basic.jobs)
    if jobs is not None:
        try:
            jobs = int(jobs)
            if jobs < 1:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）") from None

    ffmpeg_path = values.get("ffmpeg_path", config.basic.ffmpeg_path)

    return RuntimeOptions(
        jobs=jobs,
        ffmpeg_path=str(ffmpeg_path) if ffmpeg_path is not None else None,
        preview_formats=bool(values.get("preview_formats", False)),
        no_color=bool(
            values.get(
                "no_color",
                config.basic.no_color if config.basic.no_color is not None else False,
            )
        ),
        no_progress=bool(
            values.get(
                "no_progress",
                config.basic.no_progress if config.basic.no_progress is not None else False,
            )
        ),
        debug=bool(
            values.get(
                "debug",
                config.basic.debug if config.basic.debug is not None else False,
            )
        ),
    )
