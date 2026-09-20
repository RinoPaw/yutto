from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from yutto.cli.settings import YuttoConfig


def resolve_credential_options(
    tasks: Sequence[Mapping[str, Any]],
    config: YuttoConfig,
) -> list[argparse.Namespace]:
    """Merge explicit task credential options over persistent config values."""
    configured_auth = config.auth.auth if config.auth.auth is not None else ""
    configured_auth_file = None if config.auth.auth_file is None else Path(config.auth.auth_file).expanduser()
    configured_auth_profile = config.auth.auth_profile if config.auth.auth_profile is not None else "default"
    configured_sessdata = config.basic.sessdata if config.basic.sessdata is not None else ""

    return [
        argparse.Namespace(
            auth=str(task.get("auth", configured_auth)),
            auth_file=task.get("auth_file", configured_auth_file),
            auth_profile=str(task.get("auth_profile", configured_auth_profile)),
            sessdata=str(task.get("sessdata", configured_sessdata)),
        )
        for task in tasks
    ]
