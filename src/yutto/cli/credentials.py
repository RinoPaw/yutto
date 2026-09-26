from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from yutto.config import ResolvedConfig

if TYPE_CHECKING:
    from collections.abc import Sequence


def resolve_credential_options(configs: Sequence[ResolvedConfig]) -> list[argparse.Namespace]:
    """Project resolved configs onto the credential resolver's argparse-compatible input."""

    return [
        argparse.Namespace(
            auth=item.auth.cookie,
            auth_file=item.auth.file,
            auth_profile=item.auth.profile,
            sessdata=item.auth.sessdata,
        )
        for item in configs
    ]
