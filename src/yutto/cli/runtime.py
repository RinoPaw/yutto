from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from yutto.cli.settings import YuttoConfig


def resolve_runtime_options(
    values: dict[str, Any],
    config: YuttoConfig,
) -> dict[str, Any]:
    jobs = values.get("jobs", config.basic.jobs)
    if jobs is None:
        jobs = 1

    try:
        jobs = int(jobs)
        if jobs < 1:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）") from None

    return {
        "jobs": jobs,
        "ffmpeg_path": str(values.get("ffmpeg_path", "ffmpeg")),
        "no_color": bool(
            values.get(
                "no_color",
                config.basic.no_color if config.basic.no_color is not None else False,
            )
        ),
        "no_progress": bool(
            values.get(
                "no_progress",
                config.basic.no_progress if config.basic.no_progress is not None else False,
            )
        ),
        "debug": bool(
            values.get(
                "debug",
                config.basic.debug if config.basic.debug is not None else False,
            )
        ),
    }
