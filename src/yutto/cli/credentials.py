from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, cast

from yutto.cli.settings import resolved_config_from_settings
from yutto.config import ResolvedConfig

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any

    from yutto.cli.settings import YuttoConfig


def resolve_credential_options(
    configs: Sequence[ResolvedConfig] | Sequence[Mapping[str, Any]],
    config: YuttoConfig | None = None,
) -> list[argparse.Namespace]:
    """Resolve credential options from flat canonical configurations."""

    if not configs:
        return []

    if isinstance(configs[0], ResolvedConfig):
        resolved_configs = list(cast("Sequence[ResolvedConfig]", configs))
    else:
        if config is None:
            raise TypeError("config is required when resolving raw task mappings")
        configured = resolved_config_from_settings(config)
        raw_configs = cast("Sequence[Mapping[str, Any]]", configs)
        resolved_configs = [configured.with_overrides(values) for values in raw_configs]

    return [
        argparse.Namespace(
            auth=item.auth.cookie,
            auth_file=item.auth.file,
            auth_profile=item.auth.profile,
            sessdata=item.auth.sessdata,
        )
        for item in resolved_configs
    ]
