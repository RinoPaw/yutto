from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, cast

from yutto.cli.settings import scope_from_config
from yutto.scope import MISSING, Scope

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any

    from yutto.cli.settings import YuttoConfig


def resolve_credential_options(
    scopes: Sequence[Scope] | Sequence[Mapping[str, Any]],
    config: YuttoConfig | None = None,
) -> list[argparse.Namespace]:
    """Resolve credential options through the same scope chain as download options."""

    if not scopes:
        return []

    if isinstance(scopes[0], Scope):
        resolved_scopes = list(cast("Sequence[Scope]", scopes))
    else:
        if config is None:
            raise TypeError("config is required when resolving raw task mappings")
        configured = scope_from_config(config)
        raw_scopes = cast("Sequence[Mapping[str, Any]]", scopes)
        resolved_scopes = [Scope(scope, parent=configured) for scope in raw_scopes]

    return [
        argparse.Namespace(
            auth=str(_value(scope.auth.cookie, "")),
            auth_file=_auth_file(scope),
            auth_profile=str(_value(scope.auth.profile, "default")),
            sessdata=str(_value(scope.auth.sessdata, "")),
        )
        for scope in resolved_scopes
    ]


def _value(value: object, default: object) -> object:
    return default if value is MISSING or value is None else value


def _auth_file(scope: Scope) -> Path | None:
    value = scope.auth.file
    if value is MISSING or value is None:
        return None
    return value if isinstance(value, Path) else Path(value).expanduser()
