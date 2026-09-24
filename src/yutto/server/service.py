from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import TYPE_CHECKING

from yutto.auth import load_auth, validate_profile
from yutto.core.execution import (
    RequestExecutionScopeFactory,
    resolve_download_workers,
    resolve_fetch_workers,
    resolve_network_proxy,
)
from yutto.downloader.planner import resolve_block_size_bytes
from yutto.resource import resolve_danmaku_format, should_save_cover
from yutto.scope import MISSING, Scope
from yutto.server.request import scope_parser_from_settings as scope_parser_from_settings
from yutto.server.serialization import (
    event_to_json as event_to_json,
    replay_to_json as replay_to_json,
    snapshot_summary_to_json as snapshot_summary_to_json,
    snapshot_to_json as snapshot_to_json,
)
from yutto.stream import (
    resolve_audio_codecs,
    resolve_audio_quality,
    resolve_video_codec_priority,
    resolve_video_codecs,
    resolve_video_quality,
)
from yutto.utils.fetcher import resolve_proxy

if TYPE_CHECKING:
    from yutto.auth import AuthInfo


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
        try:
            value = resolve_block_size_bytes(scope)
        except ValueError as error:
            raise ServerPolicyError(f"network.block_size_bytes is invalid: {error}") from error
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
