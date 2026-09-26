from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from pathlib import Path
from types import MappingProxyType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """下载源。"""

    value: str | None = None


@dataclass(frozen=True, slots=True)
class SelectionSpec:
    """一个下载源内部的内容选择规则。"""

    expression: str | None = None
    with_extra_episodes: bool = False
    skip_preview: bool = False
    published_since: int | None = None
    published_before: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    """一次 yutto 调用自身的运行策略。"""

    jobs: int = 1
    ffmpeg_path: str | None = None
    preview_formats: bool = False
    no_color: bool = False
    no_progress: bool = False
    debug: bool = False


@dataclass(frozen=True, slots=True)
class AuthSpec:
    """认证来源、访问校验以及 auth 命令参数。"""

    cookie: str = ""
    file: Path | None = None
    profile: str = "default"
    sessdata: str = ""
    login_strict: bool = False
    vip_strict: bool = False
    mode: str = "terminal"
    poll_interval: float = 2.0
    timeout: int = 180

    def __post_init__(self) -> None:
        if isinstance(self.file, str):
            object.__setattr__(self, "file", Path(self.file).expanduser())


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """下载产物中需要获取、处理或保留的资源。"""

    video: bool = True
    audio: bool = True
    danmaku: bool = True
    subtitle: bool = True
    metadata: bool = False
    cover: bool = True
    chapter_info: bool = True
    save_cover: bool = False
    ai_translation_language: str | None = None


@dataclass(frozen=True, slots=True)
class StreamSpec:
    """音视频流质量与编码偏好。"""

    video_quality: int = 127
    audio_quality: int = 30251
    video_codec: str = "avc:copy"
    audio_codec: str = "mp4a:copy"
    video_codec_priority: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.video_codec_priority, list):
            object.__setattr__(self, "video_codec_priority", tuple(self.video_codec_priority))


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """输出目录、封装格式与命名策略。"""

    format: str = "infer"
    audio_only_format: str = "infer"
    directory: Path = Path()
    temporary_directory: Path | None = None
    overwrite: bool = False
    subpath_template: str = "{auto}"
    metadata_premiered_format: str = "%Y-%m-%d"

    def __post_init__(self) -> None:
        if isinstance(self.directory, str):
            object.__setattr__(self, "directory", Path(self.directory).expanduser())
        if isinstance(self.temporary_directory, str):
            object.__setattr__(self, "temporary_directory", Path(self.temporary_directory).expanduser())


@dataclass(frozen=True, slots=True)
class NetworkSpec:
    """网络访问、传输并发与下载节奏。"""

    proxy: str = "auto"
    fetch_workers: int = 8
    download_workers: int = 8
    block_size: float = 0.5
    download_interval: int = 0
    banned_mirrors_pattern: str | None = None

    def __post_init__(self) -> None:
        if type(self.block_size) is int:
            object.__setattr__(self, "block_size", float(self.block_size))


@dataclass(frozen=True, slots=True)
class DanmakuSpec:
    """弹幕序列化、渲染与过滤参数。"""

    format: str = "ass"
    font_size: int | None = None
    font: str = "SimHei"
    opacity: float = 0.8
    display_region_ratio: float = 1.0
    speed: float = 1.0
    block_top: bool = False
    block_bottom: bool = False
    block_scroll: bool = False
    block_reverse: bool = False
    block_fixed: bool = False
    block_special: bool = False
    block_colorful: bool = False
    block_keyword_patterns: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for field_name in ("opacity", "display_region_ratio", "speed"):
            value = getattr(self, field_name)
            if type(value) is int:
                object.__setattr__(self, field_name, float(value))
        if isinstance(self.block_keyword_patterns, list):
            object.__setattr__(self, "block_keyword_patterns", tuple(self.block_keyword_patterns))


_SPEC_TYPES: dict[str, type[Any]] = {
    "source": SourceSpec,
    "selection": SelectionSpec,
    "runtime": RuntimeSpec,
    "auth": AuthSpec,
    "resource": ResourceSpec,
    "stream": StreamSpec,
    "output": OutputSpec,
    "network": NetworkSpec,
    "danmaku": DanmakuSpec,
}
_SPEC_FIELDS = {
    section: frozenset(descriptor.name for descriptor in fields(spec_type))
    for section, spec_type in _SPEC_TYPES.items()
}
_SPEC_ANNOTATIONS = {section: get_type_hints(spec_type) for section, spec_type in _SPEC_TYPES.items()}


@dataclass(frozen=True, slots=True, init=False)
class ResolvedConfig:
    """完整、扁平、类型已归一化的 canonical 配置对象。

    对象只保存 9 个 Spec。默认值由 Spec 自身定义，构造时立即应用；
    后续覆盖通过 ``with_overrides`` 显式完成，不存在运行时继承链。
    """

    source: SourceSpec
    selection: SelectionSpec
    runtime: RuntimeSpec
    auth: AuthSpec
    resource: ResourceSpec
    stream: StreamSpec
    output: OutputSpec
    network: NetworkSpec
    danmaku: DanmakuSpec

    def __init__(
        self,
        values: Mapping[str, Any] | None = None,
        **overrides: Any,
    ) -> None:
        supplied = dict(values or {})
        supplied.update(overrides)

        section_values: dict[str, Any] = {}
        field_updates: dict[str, dict[str, Any]] = {}
        for name, value in supplied.items():
            if name in _SPEC_TYPES:
                section_values[name] = self._coerce_spec(name, value)
                continue

            section, separator, field_name = name.partition(".")
            if not separator or section not in _SPEC_TYPES or field_name not in _SPEC_FIELDS[section]:
                raise TypeError(f"unknown config field: {name}")
            field_updates.setdefault(section, {})[field_name] = value

        resolved_specs: dict[str, Any] = {}
        for section, spec_type in _SPEC_TYPES.items():
            spec = section_values.get(section, spec_type())
            updates = field_updates.get(section)
            if updates:
                spec = replace(spec, **updates)
            self._validate_spec(section, spec)
            resolved_specs[section] = spec

        object.__setattr__(self, "source", resolved_specs["source"])
        object.__setattr__(self, "selection", resolved_specs["selection"])
        object.__setattr__(self, "runtime", resolved_specs["runtime"])
        object.__setattr__(self, "auth", resolved_specs["auth"])
        object.__setattr__(self, "resource", resolved_specs["resource"])
        object.__setattr__(self, "stream", resolved_specs["stream"])
        object.__setattr__(self, "output", resolved_specs["output"])
        object.__setattr__(self, "network", resolved_specs["network"])
        object.__setattr__(self, "danmaku", resolved_specs["danmaku"])

    @staticmethod
    def _coerce_spec(section: str, value: Any) -> Any:
        spec_type = _SPEC_TYPES[section]
        if isinstance(value, spec_type):
            return value
        if isinstance(value, Mapping):
            unknown = set(value) - _SPEC_FIELDS[section]
            if unknown:
                names = ", ".join(sorted(map(str, unknown)))
                raise TypeError(f"unknown {section} fields: {names}")
            return spec_type(**value)
        raise TypeError(f"{section} must be {spec_type.__name__} or a field mapping")

    @staticmethod
    def _validate_spec(section: str, spec: Any) -> None:
        for descriptor in fields(spec):
            value = getattr(spec, descriptor.name)
            expected = _SPEC_ANNOTATIONS[section][descriptor.name]
            if not _matches_type(value, expected):
                raise TypeError(
                    f"{section}.{descriptor.name} must be {_type_name(expected)}, "
                    f"got {type(value).__name__}"
                )

    @property
    def values(self) -> Mapping[str, Any]:
        """返回当前完整配置的 canonical ``spec.field`` 值。"""
        result: dict[str, Any] = {}
        for section in _SPEC_TYPES:
            spec = getattr(self, section)
            for descriptor in fields(spec):
                result[f"{section}.{descriptor.name}"] = getattr(spec, descriptor.name)
        return MappingProxyType(result)

    def with_overrides(
        self,
        values: Mapping[str, Any] | None = None,
        **overrides: Any,
    ) -> ResolvedConfig:
        """返回仅应用给定覆盖值的新完整配置。"""
        supplied = dict(self.values)
        supplied.update(values or {})
        supplied.update(overrides)
        return ResolvedConfig(supplied)


def _matches_type(value: object, expected: object) -> bool:
    if expected is Any:
        return True

    origin = get_origin(expected)
    if origin in (Union, UnionType):
        return any(_matches_type(value, option) for option in get_args(expected))

    if origin is tuple:
        if not isinstance(value, tuple):
            return False
        args = get_args(expected)
        if len(args) == 2 and args[1] is Ellipsis:
            return all(_matches_type(item, args[0]) for item in value)
        return len(value) == len(args) and all(
            _matches_type(item, item_type) for item, item_type in zip(value, args, strict=True)
        )

    if expected is None or expected is type(None):
        return value is None
    if expected is bool:
        return type(value) is bool
    if expected is int:
        return type(value) is int
    if expected is float:
        return type(value) is float
    return isinstance(value, expected)


def _type_name(expected: object) -> str:
    origin = get_origin(expected)
    if origin in (Union, UnionType):
        return " | ".join(_type_name(option) for option in get_args(expected))
    if origin is tuple:
        args = get_args(expected)
        if len(args) == 2 and args[1] is Ellipsis:
            return f"tuple[{_type_name(args[0])}, ...]"
    if expected is type(None):
        return "None"
    if isinstance(expected, type):
        return expected.__name__
    return str(expected)


DEFAULT_CONFIG = ResolvedConfig()


__all__ = [
    "AuthSpec",
    "DEFAULT_CONFIG",
    "DanmakuSpec",
    "NetworkSpec",
    "OutputSpec",
    "ResolvedConfig",
    "ResourceSpec",
    "RuntimeSpec",
    "SelectionSpec",
    "SourceSpec",
    "StreamSpec",
]
