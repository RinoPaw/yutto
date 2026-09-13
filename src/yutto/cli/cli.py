"""Compatibility imports for the pre-refactor CLI parser API.

The application entrypoint uses :mod:`yutto.cli.parser` directly. This module keeps
older internal imports working while they are migrated.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from yutto.cli.auth_parser import (
    add_auth_logout_arguments as _add_auth_logout_arguments,
    add_auth_status_arguments as _add_auth_status_arguments,
    add_login_arguments as _add_login_arguments,
)
from yutto.cli.compat import normalize_argv
from yutto.cli.download import add_download_arguments as _add_download_arguments
from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoSettings


def cli() -> argparse.ArgumentParser:
    """Build a parser with the legacy eager defaults used by older callers."""
    settings = YuttoSettings()
    parser = build_parser()
    parser.set_defaults(
        _settings=settings,
        jobs=settings.basic.jobs,
        ffmpeg_path="ffmpeg",
        host="127.0.0.1",
        port=11223,
        allow_origin=[],
        token_file=None,
        download_root=Path(settings.basic.dir).expanduser(),
        tmp_root=None if settings.basic.tmp_dir is None else Path(settings.basic.tmp_dir).expanduser(),
        auth_file=None if settings.auth.auth_file is None else Path(settings.auth.auth_file).expanduser(),
        max_fetch_workers=max(16, settings.basic.fetch_workers),
        max_download_workers=max(16, settings.basic.num_workers),
        task_limit=256,
        server_settings=settings,
    )
    return parser


def handle_default_subcommand(argv: list[str]) -> list[str]:
    return normalize_argv(argv)


def add_download_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.argument_default = argparse.SUPPRESS
    _add_download_arguments(parser)
    parser.set_defaults(
        _settings=settings,
        jobs=settings.basic.jobs,
        ffmpeg_path="ffmpeg",
    )


def add_login_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.argument_default = argparse.SUPPRESS
    _add_login_arguments(parser)
    parser.set_defaults(_settings=settings)


def add_auth_status_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.argument_default = argparse.SUPPRESS
    _add_auth_status_arguments(parser)
    parser.set_defaults(_settings=settings)


def add_auth_logout_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.argument_default = argparse.SUPPRESS
    _add_auth_logout_arguments(parser)
    parser.set_defaults(_settings=settings)
