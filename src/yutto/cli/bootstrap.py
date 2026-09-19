from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from yutto.cli.input import path_from_cli
from yutto.cli.settings import YuttoSettings, load_settings_file, search_for_settings_file
from yutto.utils.console.logger import Logger

if TYPE_CHECKING:
    from collections.abc import Sequence


def load_config(argv: Sequence[str]) -> tuple[YuttoSettings, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=path_from_cli, default=argparse.SUPPRESS)
    args, remaining_argv = parser.parse_known_args(argv)

    config = getattr(args, "config", None)
    if config is None:
        config = search_for_settings_file()
    if config is None:
        return YuttoSettings(), remaining_argv

    Logger.info(f"发现配置文件 {config}，加载中……")
    return load_settings_file(config), remaining_argv
