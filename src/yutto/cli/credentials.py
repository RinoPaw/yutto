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
            auth=item.credential.cookie,
            auth_file=item.credential.file,
            auth_profile=item.credential.profile,
            sessdata=item.credential.sessdata,
        )
        for item in configs
    ]
