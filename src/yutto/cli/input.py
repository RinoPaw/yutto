from __future__ import annotations

import os
import re
import shlex
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.cli.compat import normalize_argv
from yutto.cli.scope import MISSING, Scope
from yutto.cli.settings import scope_from_config
from yutto.core.operation import emit_download_report
from yutto.utils.console.logger import Logger

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping
    from typing import Any

    from yutto.cli.settings import YuttoConfig


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


def _scope_values_from_cli(values: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """移除 CLI 控制字段，并在进入 Scope 前转换成权威字段名。"""
    result = dict(values)
    result.pop("command", None)
    result.pop("auth_command", None)
    result.pop("config", None)
    no_inherit = bool(result.pop("no_inherit", False))

    batch = bool(result.pop("batch", False))
    if batch and "selection_expr" not in result:
        result["selection_expr"] = "~"

    if "publication_start_time" in result:
        result["published_since"] = result.pop("publication_start_time")
    if "publication_end_time" in result:
        result["published_before"] = result.pop("publication_end_time")

    return result, no_inherit


def expand_download_scopes(
    scope: Scope,
    parser: argparse.ArgumentParser,
    config: Scope,
    *,
    no_inherit: bool = False,
) -> list[Scope]:
    """Resolve aliases and task lists by creating child scopes instead of merging dictionaries."""

    source = scope.lookup("source")
    if source is MISSING or source is None:
        raise ValueError("download source is missing")
    source = str(source)

    aliases = scope.lookup("aliases")
    if aliases is not MISSING and aliases is not None:
        source = aliases.get(source, source)

    current = Scope({**scope.values, "source": source}, parent=scope.parent)

    if not re.match(r"file://", source) and not os.path.isfile(source):  # noqa: PTH113
        return [current]

    result: list[Scope] = []
    for line in file_scheme_parser(source):
        child_raw = vars(parser.parse_args(normalize_argv(shlex.split(line))))
        if child_raw.get("command") != "download":
            raise ValueError("下载列表中只能包含 download 命令")

        child_values, child_no_inherit = _scope_values_from_cli(child_raw)
        parent = config if no_inherit or child_no_inherit else current
        child = Scope(child_values, parent=parent)
        Logger.debug(f"列表参数: {child.flatten(stop_at=config)}")
        result.extend(
            expand_download_scopes(
                child,
                parser,
                config,
                no_inherit=child_no_inherit,
            )
        )
    return result


def expand_download_values(
    values: Mapping[str, Any],
    parser: argparse.ArgumentParser,
    config: YuttoConfig,
) -> list[dict[str, Any]]:
    """Compatibility wrapper returning inherited explicit CLI values."""

    configured = scope_from_config(config)
    scope_values, no_inherit = _scope_values_from_cli(values)
    scopes = expand_download_scopes(
        Scope(scope_values, parent=configured),
        parser,
        configured,
        no_inherit=no_inherit,
    )
    return [scope.flatten(stop_at=configured) for scope in scopes]
