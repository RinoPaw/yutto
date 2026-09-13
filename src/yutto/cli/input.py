from __future__ import annotations

import copy
import os
import re
import shlex
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.core.operation import emit_download_report
from yutto.utils.console.logger import Logger
from yutto.validator import validate_basic_arguments

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable


SUBCOMMANDS = ("download", "auth", "serve")
REMOVED_TOP_LEVEL_SUBCOMMANDS = ("login",)


def normalize_argv(argv: list[str]) -> list[str]:
    """Insert the legacy implicit download subcommand when needed."""
    if not argv:
        return ["download"]
    if argv[0] in REMOVED_TOP_LEVEL_SUBCOMMANDS:
        return argv
    if argv[0] not in SUBCOMMANDS and argv[0] not in {"-v", "--version"}:
        argv.insert(0, "download")
    return argv


def path_from_cli(path: str) -> Path:
    """从命令行参数获取路径，支持 ~，以便配置中使用 ~。"""
    return Path(path).expanduser()


def is_comment(line: str) -> bool:
    return line.startswith("#")


def alias_parser(file_path: str) -> dict[str, str]:
    result: dict[str, str] = {}
    re_alias_splitter = re.compile(r"[\s=]")
    with path_from_cli(file_path).open("r") as f_alias:
        for line in f_alias:
            line = line.strip()
            if not line or is_comment(line):
                continue
            alias, url = re_alias_splitter.split(line, maxsplit=1)
            result[alias] = url
    return result


def file_scheme_parser(url: str) -> list[str]:
    file_url = urllib.parse.urlparse(url).path
    file_path = path_from_cli(urllib.request.url2pathname(file_url))
    emit_download_report(f"解析下载列表 {file_path} 中...")
    result: list[str] = []
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or is_comment(line):
                continue
            result.append(line)
    return result


def expand_download_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    validate: Callable[[argparse.Namespace], None] = validate_basic_arguments,
) -> list[argparse.Namespace]:
    """Resolve aliases and recursively expand file-list inputs."""
    args = copy.copy(args)
    validate(args)

    alias_map: dict[str, str] = args.aliases if args.aliases is not None else {}
    if args.source in alias_map:
        args.source = alias_map[args.source]

    if not re.match(r"file://", args.source) and not os.path.isfile(args.source):  # noqa: PTH113
        return [args]

    result: list[argparse.Namespace] = []
    for line in file_scheme_parser(args.source):
        line_argv = normalize_argv(shlex.split(line))
        local_args = parser.parse_args(line_argv, args)
        if local_args.no_inherit:
            local_args = parser.parse_args(line_argv)
        Logger.debug(f"列表参数: {local_args}")
        result.extend(expand_download_args(local_args, parser, validate=validate))
    return result
