from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from string import Formatter
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar, cast

from pydantic import BaseModel

from yutto.auth import load_auth, validate_profile
from yutto.cli.settings import scope_from_config
from yutto.core.execution import (
    RequestExecutionScopeFactory,
    resolve_download_workers,
    resolve_fetch_workers,
    resolve_network_proxy,
)
from yutto.downloader.planner import MEBIBYTE, resolve_block_size_bytes
from yutto.media import Media
from yutto.resource import resolve_danmaku_format, should_save_cover
from yutto.scope import MISSING, Scope
from yutto.stream import (
    resolve_audio_codecs,
    resolve_audio_quality,
    resolve_video_codec_priority,
    resolve_video_codecs,
    resolve_video_quality,
)
from yutto.types import BilibiliId
from yutto.utils.fetcher import resolve_proxy
from yutto.utils.time import parse_local_timestamp

if TYPE_CHECKING:
    from collections.abc import Callable

    from yutto.auth import AuthInfo
    from yutto.cli.settings import YuttoConfig
    from yutto.runtime import EventReplay, TaskEvent, TaskSnapshot

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
PayloadT = TypeVar("PayloadT")
ResultT = TypeVar("ResultT")

_CREDENTIAL_FIELDS = frozenset(
    {
        "api_key",
        "auth",
        "authorization",
        "bili_jct",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "password",
        "secret",
        "sessdata",
        "token",
    }
)

_RPC_TOP_LEVEL_FIELDS = frozenset(
    {
        "source",
        "access",
        "batch",
        "with_extra_episodes",
        "selection",
        "resources",
        "stream",
        "output",
        "network",
        "danmaku",
    }
)


class ServerPolicyError(ValueError):
    """A request violates a local server boundary."""


@dataclass(frozen=True, slots=True)
class ServerPolicyOptions:
    """Filesystem, authentication, and concurrency boundaries for the server."""

    download_root: Path
    tmp_root: Path
    auth_file: Path
    max_fetch_workers: int = 8
    max_download_workers: int = 8
    min_block_size_bytes: int = 64 * 1024
    max_block_size_bytes: int = 64 * 1024 * 1024
    allowed_video_save_codecs: frozenset[str] | None = None
    allowed_audio_save_codecs: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.max_fetch_workers < 1:
            raise ValueError("max_fetch_workers must be at least 1")
        if self.max_download_workers < 1:
            raise ValueError("max_download_workers must be at least 1")
        if self.min_block_size_bytes < 1:
            raise ValueError("min_block_size_bytes must be at least 1")
        if self.max_block_size_bytes < self.min_block_size_bytes:
            raise ValueError("max_block_size_bytes must be at least min_block_size_bytes")

        object.__setattr__(self, "download_root", self.download_root.expanduser().resolve())
        object.__setattr__(self, "tmp_root", self.tmp_root.expanduser().resolve())
        object.__setattr__(self, "auth_file", self.auth_file.expanduser().resolve())


class ServerPolicy:
    """Apply server-owned limits before a Scope enters the task runtime."""

    def __init__(self, options: ServerPolicyOptions):
        self.options = options

    def prepare_scope(self, scope: Scope) -> Scope:
        """Return a child Scope with server-owned absolute output paths."""
        self._validate_workers(scope)
        self._validate_proxy(scope)
        self._validate_auth_profile(scope)
        self._validate_block_size(scope)
        self._validate_save_codecs(scope)
        self._validate_scope_values(scope)
        self._validate_subpath_template(_scope_text(scope.output.subpath_template, "{auto}"))

        directory = scope.output.directory
        request_directory = Path() if directory is MISSING or directory is None else Path(directory)
        output_directory = self._resolve_request_path(
            request_directory,
            root=self.options.download_root,
            field="output.directory",
        )

        temporary = scope.output.temporary_directory
        temporary_directory = (
            self.options.tmp_root
            if temporary is MISSING or temporary is None
            else self._resolve_request_path(
                Path(temporary),
                root=self.options.tmp_root,
                field="output.temporary_directory",
            )
        )
        return Scope(
            {
                "output.directory": output_directory,
                "output.temporary_directory": temporary_directory,
            },
            parent=scope,
        )

    def build_scope_factory(self) -> RequestExecutionScopeFactory:
        """Build the shared Scope-to-runtime boundary used by server tasks."""
        return RequestExecutionScopeFactory(
            self.resolve_credentials,
            enforce_output_boundary=True,
        )

    def resolve_credentials(self, scope: Scope) -> AuthInfo | None:
        """Resolve one auth profile without attaching credentials to the Scope."""
        try:
            return load_auth(self.options.auth_file, _auth_profile(scope))
        except ValueError as error:
            raise ServerPolicyError(str(error)) from error

    def _validate_workers(self, scope: Scope) -> None:
        self._validate_worker_count(
            "network.fetch_workers",
            resolve_fetch_workers(scope),
            self.options.max_fetch_workers,
        )
        self._validate_worker_count(
            "network.download_workers",
            resolve_download_workers(scope),
            self.options.max_download_workers,
        )

    @staticmethod
    def _validate_proxy(scope: Scope) -> None:
        try:
            resolve_proxy(resolve_network_proxy(scope))
        except ValueError as error:
            raise ServerPolicyError(str(error)) from error

    @staticmethod
    def _validate_auth_profile(scope: Scope) -> None:
        try:
            validate_profile(_auth_profile(scope))
        except ValueError as error:
            raise ServerPolicyError(str(error)) from error

    def _validate_block_size(self, scope: Scope) -> None:
        value = resolve_block_size_bytes(scope)
        if not self.options.min_block_size_bytes <= value <= self.options.max_block_size_bytes:
            raise ServerPolicyError(
                "network.block_size_bytes must be between "
                f"{self.options.min_block_size_bytes} and {self.options.max_block_size_bytes}"
            )

    def _validate_save_codecs(self, scope: Scope) -> None:
        _, video_save_codec = resolve_video_codecs(scope)
        _, audio_save_codec = resolve_audio_codecs(scope)
        if (
            self.options.allowed_video_save_codecs is not None
            and video_save_codec not in self.options.allowed_video_save_codecs
        ):
            raise ServerPolicyError(f"unsupported video save codec: {video_save_codec}")
        if (
            self.options.allowed_audio_save_codecs is not None
            and audio_save_codec not in self.options.allowed_audio_save_codecs
        ):
            raise ServerPolicyError(f"unsupported audio save codec: {audio_save_codec}")

    @staticmethod
    def _validate_scope_values(scope: Scope) -> None:
        resolve_video_quality(scope)
        resolve_audio_quality(scope)
        resolve_video_codec_priority(scope)
        resolve_danmaku_format(scope)
        should_save_cover(scope)

        output_format = scope.output.format
        if output_format is not MISSING and output_format not in {"infer", "mp4", "mkv", "mov"}:
            raise ServerPolicyError(f"unsupported output format: {output_format}")
        audio_only_format = scope.output.audio_only_format
        if audio_only_format is not MISSING and audio_only_format not in {
            "infer",
            "m4a",
            "aac",
            "mp3",
            "flac",
            "mp4",
            "mkv",
            "mov",
        }:
            raise ServerPolicyError(f"unsupported audio-only output format: {audio_only_format}")

    @staticmethod
    def _validate_worker_count(field: str, value: int, maximum: int) -> None:
        if value < 1 or value > maximum:
            raise ServerPolicyError(f"{field} must be between 1 and {maximum}")

    @staticmethod
    def _resolve_request_path(path: Path, *, root: Path, field: str) -> Path:
        # anchor 检查覆盖 Windows 上 is_absolute() 为 False 的盘符相对/根路径（如 "/x"、"C:x"）
        if path.is_absolute() or path.anchor:
            raise ServerPolicyError(f"{field} must be relative to its configured root")
        if ".." in path.parts:
            raise ServerPolicyError(f"{field} must not contain '..'")

        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root):
            raise ServerPolicyError(f"{field} escapes its configured root")
        return resolved

    @staticmethod
    def _validate_subpath_template(template: str) -> None:
        path = Path(template)
        if path.is_absolute() or path.anchor:
            raise ServerPolicyError("output.subpath_template must be relative")
        if ".." in path.parts:
            raise ServerPolicyError("output.subpath_template must not contain '..'")
        allowed_fields = {
            "auto",
            "title",
            "id",
            "aid",
            "bvid",
            "name",
            "username",
            "series_title",
            "pubdate",
            "download_date",
            "owner_uid",
            "owner_uname",
        }
        time_field_pattern = re.compile(r"\{(?:pubdate|download_date)@[^{}]{1,128}\}")
        template_for_validation = time_field_pattern.sub("{download_date}", template)
        try:
            parsed_fields = list(Formatter().parse(template_for_validation))
        except ValueError as error:
            raise ServerPolicyError("output.subpath_template is invalid") from error
        for _, field_name, format_spec, conversion in parsed_fields:
            if field_name is None:
                continue
            if field_name not in allowed_fields:
                raise ServerPolicyError(f"output.subpath_template contains unsupported field: {field_name}")
            if conversion not in {None, "s", "r", "a"}:
                raise ServerPolicyError("output.subpath_template contains an unsupported conversion")
            ServerPolicy._validate_format_spec(format_spec or "")

    @staticmethod
    def _validate_format_spec(format_spec: str) -> None:
        if not format_spec:
            return
        if len(format_spec) > 32 or "{" in format_spec or "}" in format_spec:
            raise ServerPolicyError("output.subpath_template format spec is too complex")
        if any(separator in format_spec for separator in ("/", "\\", "..")):
            raise ServerPolicyError("output.subpath_template format spec contains an unsafe fill")
        if len(format_spec) >= 2 and format_spec[1] in "<>=^" and format_spec[0] == ".":
            raise ServerPolicyError("output.subpath_template format spec contains an unsafe fill")
        if any(int(width) > 256 for width in re.findall(r"\d+", format_spec)):
            raise ServerPolicyError("output.subpath_template format width is too large")


def scope_parser_from_settings(settings: YuttoConfig) -> Callable[[object], Scope]:
    """Build the server wire-format -> Scope adapter with config inheritance."""
    configured_values = dict(scope_from_config(settings).flatten())
    configured_values.pop("output.directory", None)
    configured_values.pop("output.temporary_directory", None)
    configured = Scope(configured_values)

    def parse(payload: object) -> Scope:
        return Scope(_scope_values_from_rpc_payload(payload, configured), parent=configured)

    parse({"source": {"url": "yutto-server-default-validation"}})
    return parse


def _scope_values_from_rpc_payload(payload: object, parent: Scope) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("request must be an object")
    request = cast("dict[str, Any]", payload)
    unknown = request.keys() - _RPC_TOP_LEVEL_FIELDS
    if unknown:
        raise TypeError(f"unknown request fields: {', '.join(sorted(unknown))}")

    values: dict[str, Any] = {}

    source = _section(request, "source", {"url"}, required=True)
    source_value = source.get("url")
    if not isinstance(source_value, str) or not source_value:
        raise ValueError("source.url must be a non-empty string")
    values["source.value"] = source_value

    _copy_section(
        request,
        "access",
        {
            "auth_profile": "auth.profile",
            "login_strict": "auth.login_strict",
            "vip_strict": "auth.vip_strict",
        },
        values,
    )
    selection = _section(
        request,
        "selection",
        {"expression", "skip_preview", "start_time", "end_time"},
    )
    for field, path in {
        "expression": "selection.expression",
        "skip_preview": "selection.skip_preview",
    }.items():
        if field in selection:
            values[path] = selection[field]
    for field, path in {
        "start_time": "selection.published_since",
        "end_time": "selection.published_before",
    }.items():
        if field not in selection:
            continue
        value = selection[field]
        if value is None:
            values[path] = None
        elif not isinstance(value, str):
            raise TypeError(f"selection.{field} must be a string or null")
        else:
            values[path] = parse_local_timestamp(value)
    if "with_extra_episodes" in request:
        values["selection.with_extra_episodes"] = request["with_extra_episodes"]
    if request.get("batch") and "expression" not in selection:
        values["selection.expression"] = "~"

    _copy_section(
        request,
        "resources",
        {
            "video": "resource.video",
            "audio": "resource.audio",
            "danmaku": "resource.danmaku",
            "subtitle": "resource.subtitle",
            "metadata": "resource.metadata",
            "cover": "resource.cover",
            "chapter_info": "resource.chapter_info",
            "save_cover": "resource.save_cover",
            "ai_translation_language": "resource.ai_translation_language",
        },
        values,
    )

    stream = _section(
        request,
        "stream",
        {
            "video_quality",
            "audio_quality",
            "video_download_codec",
            "video_save_codec",
            "video_download_codec_priority",
            "audio_download_codec",
            "audio_save_codec",
        },
    )
    if "video_quality" in stream:
        values["stream.video_quality"] = stream["video_quality"]
    if "audio_quality" in stream:
        values["stream.audio_quality"] = stream["audio_quality"]
    if "video_download_codec_priority" in stream:
        values["stream.video_codec_priority"] = stream["video_download_codec_priority"]
    if "video_download_codec" in stream or "video_save_codec" in stream:
        default_download, default_save = resolve_video_codecs(parent)
        download = stream.get("video_download_codec", default_download)
        save = stream.get("video_save_codec", default_save)
        if not isinstance(download, str) or not isinstance(save, str):
            raise TypeError("video codec fields must be strings")
        values["stream.video_codec"] = f"{download}:{save}"
    if "audio_download_codec" in stream or "audio_save_codec" in stream:
        default_download, default_save = resolve_audio_codecs(parent)
        download = stream.get("audio_download_codec", default_download)
        save = stream.get("audio_save_codec", default_save)
        if not isinstance(download, str) or not isinstance(save, str):
            raise TypeError("audio codec fields must be strings")
        values["stream.audio_codec"] = f"{download}:{save}"

    output = _section(
        request,
        "output",
        {
            "directory",
            "temporary_directory",
            "format",
            "audio_only_format",
            "overwrite",
            "subpath_template",
            "metadata_format_premiered",
        },
    )
    if "directory" in output:
        values["output.directory"] = _path_value(output["directory"], allow_none=False)
    if "temporary_directory" in output:
        values["output.temporary_directory"] = _path_value(output["temporary_directory"], allow_none=True)
    for wire, canonical in {
        "format": "output.format",
        "audio_only_format": "output.audio_only_format",
        "overwrite": "output.overwrite",
        "subpath_template": "output.subpath_template",
        "metadata_format_premiered": "output.metadata_premiered_format",
    }.items():
        if wire in output:
            values[canonical] = output[wire]

    network = _section(
        request,
        "network",
        {
            "proxy",
            "fetch_workers",
            "download_workers",
            "block_size_bytes",
            "download_interval",
            "banned_mirrors_pattern",
        },
    )
    for wire, canonical in {
        "proxy": "network.proxy",
        "fetch_workers": "network.fetch_workers",
        "download_workers": "network.download_workers",
        "download_interval": "network.download_interval",
        "banned_mirrors_pattern": "network.banned_mirrors_pattern",
    }.items():
        if wire in network:
            values[canonical] = network[wire]
    if "block_size_bytes" in network:
        block_size = network["block_size_bytes"]
        if isinstance(block_size, bool) or not isinstance(block_size, (int, float)):
            raise TypeError("network.block_size_bytes must be numeric")
        values["network.block_size"] = float(block_size) / MEBIBYTE

    _copy_section(
        request,
        "danmaku",
        {
            "format": "danmaku.format",
            "font_size": "danmaku.font_size",
            "font": "danmaku.font",
            "opacity": "danmaku.opacity",
            "display_region_ratio": "danmaku.display_region_ratio",
            "speed": "danmaku.speed",
            "block_top": "danmaku.block_top",
            "block_bottom": "danmaku.block_bottom",
            "block_scroll": "danmaku.block_scroll",
            "block_reverse": "danmaku.block_reverse",
            "block_special": "danmaku.block_special",
            "block_colorful": "danmaku.block_colorful",
            "block_keyword_patterns": "danmaku.block_keyword_patterns",
        },
        values,
    )
    return values


def _section(
    request: dict[str, Any],
    name: str,
    allowed: set[str],
    *,
    required: bool = False,
) -> dict[str, Any]:
    if name not in request:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    value = request[name]
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    section = cast("dict[str, Any]", value)
    unknown = section.keys() - allowed
    if unknown:
        raise TypeError(f"unknown {name} fields: {', '.join(sorted(unknown))}")
    return section


def _copy_section(
    request: dict[str, Any],
    name: str,
    paths: dict[str, str],
    target: dict[str, Any],
) -> dict[str, Any]:
    section = _section(request, name, set(paths))
    for field, path in paths.items():
        if field in section:
            target[path] = section[field]
    return section


def _path_value(value: object, *, allow_none: bool) -> Path | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise TypeError("path fields must be strings")
    return Path(value)


def _auth_profile(scope: Scope) -> str:
    value = scope.auth.profile
    if value is MISSING or value is None:
        return "default"
    if not isinstance(value, str):
        raise ValueError("auth profile must be a string")
    return value


def _scope_text(value: object, default: str) -> str:
    if value is MISSING:
        return default
    if not isinstance(value, str):
        raise ValueError("expected a string Scope value")
    return value


def snapshot_to_json(snapshot: TaskSnapshot[PayloadT, ResultT]) -> dict[str, object]:
    """Convert a task snapshot into a credential-safe JSON object."""
    result = snapshot_summary_to_json(snapshot)
    if snapshot.error is not None:
        error: dict[str, JsonValue] = {
            "code": snapshot.error.code,
            "type": snapshot.error.type,
            "message": snapshot.error.message,
        }
        if snapshot.error.truncated:
            error["truncated"] = True
        result["error"] = error
    result["payload"] = _to_json_value(snapshot.payload)
    result["result"] = _to_json_value(snapshot.result)
    return result


def snapshot_summary_to_json(snapshot: TaskSnapshot[PayloadT, ResultT]) -> dict[str, object]:
    """Convert a task snapshot without retaining or expanding its payload."""
    error: dict[str, JsonValue] | None = None
    if snapshot.error is not None:
        error = {"code": snapshot.error.code, "type": snapshot.error.type}
        if snapshot.error.truncated:
            error["truncated"] = True
    return {
        "task_id": snapshot.task_id,
        "state": snapshot.state.value,
        "error": error,
        "created_at": snapshot.created_at.isoformat(),
        "started_at": snapshot.started_at.isoformat() if snapshot.started_at is not None else None,
        "finished_at": snapshot.finished_at.isoformat() if snapshot.finished_at is not None else None,
        "last_event_seq": snapshot.last_event_seq,
    }


def event_to_json(event: TaskEvent) -> dict[str, object]:
    """Convert a runtime event into a credential-safe JSON object."""
    return {
        "task_id": event.task_id,
        "seq": event.seq,
        "kind": event.kind,
        "state": event.state.value,
        "created_at": event.created_at.isoformat(),
        "data": _to_json_value(event.data),
    }


def replay_to_json(replay: EventReplay) -> dict[str, object]:
    """Convert a bounded event replay into a JSON object."""
    return {
        "task_id": replay.task_id,
        "after_seq": replay.after_seq,
        "events": [event_to_json(event) for event in replay.events],
        "truncated": replay.truncated,
    }


def _scope_to_json(scope: Scope) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for path, value in scope.flatten().items():
        section, field = path.split(".", 1)
        if _is_credential_field(field):
            continue
        section_value = result.setdefault(section, {})
        if not isinstance(section_value, dict):
            raise TypeError(f"invalid Scope section: {section}")
        section_value[field] = _to_json_value(value)
    return result


def _to_json_value(value: object) -> JsonValue:
    if isinstance(value, Scope):
        return _scope_to_json(value)
    if isinstance(value, Enum):
        return _to_json_value(value.value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, BilibiliId):
        return str(value)
    if isinstance(value, Media):
        result: dict[str, JsonValue] = {"type": type(value).__name__}
        for item_field in fields(value):
            result[item_field.name] = _to_json_value(getattr(value, item_field.name))
        return result
    if is_dataclass(value) and not isinstance(value, type):
        result = {}
        for item_field in fields(value):
            if _is_credential_field(item_field.name):
                continue
            result[item_field.name] = _to_json_value(getattr(value, item_field.name))
        return result
    if isinstance(value, BaseModel):
        return _to_json_value(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            json_key = str(key)
            if _is_credential_field(json_key):
                continue
            if json_key.casefold() == "proxy" and isinstance(item, str):
                result[json_key] = _sanitize_proxy(item)
                continue
            result[json_key] = _to_json_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_to_json_value(item) for item in value]
    raise TypeError(f"value of type {type(value).__name__} is not JSON compatible")


def _is_credential_field(field: str) -> bool:
    normalized = field.casefold().replace("-", "_")
    return normalized in _CREDENTIAL_FIELDS or normalized.endswith(
        ("_api_key", "_cookie", "_credential", "_password", "_secret", "_token")
    )


def _sanitize_proxy(proxy: str) -> str:
    scheme_separator = proxy.find("://")
    if scheme_separator < 0:
        return proxy

    authority_start = scheme_separator + 3
    authority_end = len(proxy)
    for separator in "/?#":
        if (index := proxy.find(separator, authority_start)) >= 0:
            authority_end = min(authority_end, index)
    credential_separator = proxy.rfind("@", authority_start, authority_end)
    if credential_separator < 0:
        return proxy
    return f"{proxy[: scheme_separator + 3]}{proxy[credential_separator + 1 :]}"
