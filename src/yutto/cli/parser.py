from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from yutto.__version__ import VERSION as yutto_version
from yutto.cli.auth_parser import add_auth_subcommands
from yutto.cli.download import add_download_arguments
from yutto.cli.input import normalize_argv, path_from_cli
from yutto.cli.serve import add_serve_arguments
from yutto.cli.settings import YuttoSettings, load_settings_file, search_for_settings_file
from yutto.utils.console.logger import Logger

if TYPE_CHECKING:
    from pathlib import Path


def parse_config_path() -> Path | None:
    pre_parser = argparse.ArgumentParser(description="yutto pre parser", add_help=False)
    pre_parser.add_argument(
        "--config",
        type=path_from_cli,
        default=search_for_settings_file(),
        help="配置文件路径（UTF-8 格式）",
    )
    args, _ = pre_parser.parse_known_args()
    return args.config


def load_cli_settings() -> YuttoSettings:
    settings_file = parse_config_path()
    if settings_file is None:
        return YuttoSettings()
    Logger.info(f"发现配置文件 {settings_file}，加载中……")
    return load_settings_file(settings_file)


def build_parser() -> argparse.ArgumentParser:
    """Build the complete yutto command-line grammar."""
    settings = load_cli_settings()
    parser = argparse.ArgumentParser(description="yutto 一个可爱且任性的 B 站视频下载器", prog="yutto")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {yutto_version}")

    subparsers = parser.add_subparsers(dest="command", help="支持的子命令")

    download_parser = subparsers.add_parser("download", help="下载视频")
    add_download_arguments(download_parser, settings)

    auth_parser = subparsers.add_parser("auth", help="认证相关命令")
    add_auth_subcommands(auth_parser, settings)

    serve_parser = subparsers.add_parser("serve", help="启动本地 JSON-RPC server")
    add_serve_arguments(serve_parser, settings)

    return parser


__all__ = ["build_parser", "normalize_argv"]
