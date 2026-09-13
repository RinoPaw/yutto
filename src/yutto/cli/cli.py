from __future__ import annotations

from yutto.cli.auth_parser import (
    add_auth_logout_arguments,
    add_auth_status_arguments,
    add_login_arguments,
)
from yutto.cli.download import add_download_arguments
from yutto.cli.parser import build_parser, normalize_argv


# Compatibility aliases for existing internal imports and tests.
cli = build_parser
handle_default_subcommand = normalize_argv

__all__ = [
    "add_auth_logout_arguments",
    "add_auth_status_arguments",
    "add_download_arguments",
    "add_login_arguments",
    "build_parser",
    "cli",
    "handle_default_subcommand",
    "normalize_argv",
]
