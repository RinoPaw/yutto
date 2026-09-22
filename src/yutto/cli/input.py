from __future__ import annotations

import os
import re
import shlex
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.cli.compat import normalize_argv
from yutto.cli.settings import scope_from_config
from yutto.core.operation import emit_download_report
from yutto.scope import MISSING, Scope
from yutto.utils.console.logger import Logger

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping
    from typing import Any

    from yutto.cli.settings import YuttoConfig


_CLI_SCOPE_PATHS = {
    "source": "source.value",
    "aliases": "source.aliases",
    "selection_expr": "selection.expression",
    "with_extra_episodes": "selection.with_extra_episodes",
    "skip_preview": "selection.skip_preview",
    "publication_start_time": "selection.published_since",
    "publication_end_time": "selection.published_before",
    "jobs": "runtime.jobs",
    "ffmpeg_path": "runtime.ffmpeg_path",
    "preview_formats": "runtime.preview_formats",
    "no_color": "runtime.no_color",
    "no_progress": "runtime.no_progress",
    "debug": "runtime.debug",
    "auth": "auth.cookie",
    "auth_file": "auth.file",
    "auth_profile": "auth.profile",
    "sessdata": "auth.sessdata",
    "login_strict": "auth.login_strict",
    "vip_strict": "auth.vip_strict",
    "mode": "auth.mode",
    "poll_interval": "auth.poll_interval",
    "timeout": "auth.timeout",
    "require_video": "resource.video",
    "require_audio": "resource.audio",
    "require_danmaku": "resource.danmaku",
    "require_subtitle": "resource.subtitle",
    "require_metadata": "resource.metadata",
    "require_cover": "resource.cover",
    "require_chapter_info": "resource.chapter_info",
    "save_cover": "resource.save_cover",
    "ai_translation_language": "resource.ai_translation_language",
    "video_quality": "stream.video_quality",
    "audio_quality": "stream.audio_quality",
    "vcodec": "stream.video_codec",
    "acodec": "stream.audio_codec",
    "download_vcodec_priority": "stream.video_codec_priority",
    "output_format": "output.format",
    "output_format_audio_only": "output.audio_only_format",
    "dir": "output.directory",
    "tmp_dir": "output.temporary_directory",
    "overwrite": "output.overwrite",
    "subpath_template": "output.subpath_template",
    "metadata_premiered_format": "output.metadata_premiered_format",
    "proxy": "network.proxy",
    "fetch_workers": "network.fetch_workers",
    "download_workers": "network.download_workers",
    "block_size": "network.block_size",
    "download_interval": "network.download_interval",
    "banned_mirrors_pattern": "network.banned_mirrors_pattern",
    "danmaku_format": "danmaku.format",
    "danmaku_font_size": "danmaku.font_size",
    "danmaku_font": "danmaku.font",
    "danmaku_opacity": "danmaku.opacity",
    "danmaku_display_region_ratio": "danmaku.display_region_ratio",
    "danmaku_speed": "danmaku.speed",
    "danmaku_block_top": "danmaku.block_top",
    "danmaku_block_bottom": "danmaku.block_bottom",
    "danmaku_block_scroll": "danmaku.block_scroll",
    "danmaku_block_reverse": "danmaku.block_reverse",
    "danmaku_block_fixed": "danmaku.block_fixed",
    "danmaku_block_special": "danmaku.block_special",
    "danmaku_block_colorful": "danmaku.block_colorful",
    "danmaku_block_keyword_patterns": "danmaku.block_keyword_patterns",
}
_CLI_CONTROL_FIELDS = frozenset({"command", "auth_command", "config", "no_inherit", "batch"})


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


def scope_values_from_cli(values: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """把 argparse 字段转换成 Scope 的权威 ``spec.field`` 路径。"""
    result: dict[str, Any] = {}
    unknown: list[str] = []

    for name, value in values.items():
        if name in _CLI_CONTROL_FIELDS:
            continue
        path = _CLI_SCOPE_PATHS.get(name)
        if path is None:
            unknown.append(name)
            continue
        result[path] = value

    if unknown:
        names = ", ".join(sorted(unknown))
        raise TypeError(f"CLI fields without Scope mapping: {names}")

    if values.get("batch") and "selection.expression" not in result:
        result["selection.expression"] = "~"

    return result, bool(values.get("no_inherit", False))


def expand_download_scopes(
    scope: Scope,
    parser: argparse.ArgumentParser,
    config: Scope,
    *,
    no_inherit: bool = False,
) -> list[Scope]:
    """Resolve aliases and task lists by creating child scopes instead of merging dictionaries."""

    source = scope.source.value
    if source is MISSING or source is None:
        raise ValueError("download source is missing")
    source = str(source)

    aliases = scope.source.aliases
    if aliases is not MISSING and aliases is not None:
        source = aliases.get(source, source)

    current = Scope({**scope.values, "source.value": source}, parent=scope.parent)

    if not re.match(r"file://", source) and not os.path.isfile(source):  # noqa: PTH113
        return [current]

    result: list[Scope] = []
    for line in file_scheme_parser(source):
        child_raw = vars(parser.parse_args(normalize_argv(shlex.split(line))))
        if child_raw.get("command") != "download":
            raise ValueError("下载列表中只能包含 download 命令")

        child_values, child_no_inherit = scope_values_from_cli(child_raw)
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
    """Return canonical explicit Scope paths for expanded download tasks."""

    configured = scope_from_config(config)
    scope_values, no_inherit = scope_values_from_cli(values)
    scopes = expand_download_scopes(
        Scope(scope_values, parent=configured),
        parser,
        configured,
        no_inherit=no_inherit,
    )
    return [scope.flatten(stop_at=configured) for scope in scopes]
