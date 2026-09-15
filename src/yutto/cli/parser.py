from __future__ import annotations

import argparse

from yutto.__version__ import VERSION as yutto_version
from yutto.cli.auth_parser import add_auth_subcommands
from yutto.cli.download import add_download_arguments
from yutto.cli.serve import add_serve_arguments


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line grammar without loading application settings."""
    parser = argparse.ArgumentParser(description="yutto 一个可爱且任性的 B 站视频下载器", prog="yutto")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {yutto_version}")

    subparsers = parser.add_subparsers(dest="command", help="支持的子命令", required=True)

    download_parser = subparsers.add_parser(
        "download",
        help="下载视频",
        argument_default=argparse.SUPPRESS,
    )
    add_download_arguments(download_parser)

    auth_parser = subparsers.add_parser(
        "auth",
        help="认证相关命令",
        argument_default=argparse.SUPPRESS,
    )
    add_auth_subcommands(auth_parser)

    serve_parser = subparsers.add_parser(
        "serve",
        help="启动本地 JSON-RPC server",
        argument_default=argparse.SUPPRESS,
    )
    add_serve_arguments(serve_parser)

    return parser
