from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto.cli.input import path_from_cli
from yutto.cli.settings import YuttoSettings, load_settings_file, search_for_settings_file
from yutto.utils.console.logger import Logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class BootstrapOptions:
    config: Path | None


def parse_bootstrap_args(argv: Sequence[str]) -> BootstrapOptions:
    """Read options needed before the full command grammar is parsed."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=path_from_cli, default=argparse.SUPPRESS)
    args, _ = parser.parse_known_args(argv)
    config = args.config if hasattr(args, "config") else search_for_settings_file()
    return BootstrapOptions(config=config)


def load_cli_settings(options: BootstrapOptions) -> YuttoSettings:
    if options.config is None:
        return YuttoSettings()
    Logger.info(f"发现配置文件 {options.config}，加载中……")
    return load_settings_file(options.config)
