from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Mapping


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()

ScopeText: TypeAlias = str | None | _Missing
ScopeBool: TypeAlias = bool | None | _Missing
ScopeInt: TypeAlias = int | None | _Missing
ScopeFloat: TypeAlias = float | int | None | _Missing
ScopePath: TypeAlias = Path | str | None | _Missing


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """下载源。"""

    value: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class SelectionSpec:
    """一个下载源内部的内容选择规则。"""

    expression: ScopeText = MISSING
    with_extra_episodes: ScopeBool = MISSING
    skip_preview: ScopeBool = MISSING
    published_since: ScopeInt = MISSING
    published_before: ScopeInt = MISSING


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    """一次 yutto 调用自身的运行策略。"""

    jobs: ScopeInt = MISSING
    ffmpeg_path: ScopeText = MISSING
    preview_formats: ScopeBool = MISSING
    no_color: ScopeBool = MISSING
    no_progress: ScopeBool = MISSING
    debug: ScopeBool = MISSING


@dataclass(frozen=True, slots=True)
class AuthSpec:
    """认证来源、访问校验以及 auth 命令参数。"""

    cookie: ScopeText = MISSING
    file: ScopePath = MISSING
    profile: ScopeText = MISSING
    sessdata: ScopeText = MISSING
    login_strict: ScopeBool = MISSING
    vip_strict: ScopeBool = MISSING
    mode: ScopeText = MISSING
    poll_interval: ScopeFloat = MISSING
    timeout: ScopeInt = MISSING


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """下载产物中需要获取、处理或保留的资源。"""

    video: ScopeBool = MISSING
    audio: ScopeBool = MISSING
    danmaku: ScopeBool = MISSING
    subtitle: ScopeBool = MISSING
    metadata: ScopeBool = MISSING
    cover: ScopeBool = MISSING
    chapter_info: ScopeBool = MISSING
    save_cover: ScopeBool = MISSING
    ai_translation_language: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class StreamSpec:
    """音视频流质量与编码偏好。"""

    video_quality: ScopeInt = MISSING
    audio_quality: ScopeInt = MISSING
    video_codec: ScopeText = MISSING
    audio_codec: ScopeText = MISSING
    video_codec_priority: tuple[str, ...] | None | _Missing = MISSING

    def __post_init__(self) -> None:
        if isinstance(self.video_codec_priority, list):
            object.__setattr__(self, "video_codec_priority", tuple(self.video_codec_priority))


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """输出目录、封装格式与命名策略。"""

    format: ScopeText = MISSING
    audio_only_format: ScopeText = MISSING
    directory: ScopePath = MISSING
    temporary_directory: ScopePath = MISSING
    overwrite: ScopeBool = MISSING
    subpath_template: ScopeText = MISSING
    metadata_premiered_format: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class NetworkSpec:
    """网络访问、传输并发与下载节奏。"""

    proxy: ScopeText = MISSING
    fetch_workers: ScopeInt = MISSING
    download_workers: ScopeInt = MISSING
    block_size: ScopeFloat = MISSING
    download_interval: ScopeInt = MISSING
    banned_mirrors_pattern: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class DanmakuSpec:
    """弹幕序列化、渲染与过滤参数。"""

    format: ScopeText = MISSING
    font_size: ScopeInt = MISSING
    font: ScopeText = MISSING
    opacity: ScopeFloat = MISSING
    display_region_ratio: ScopeFloat = MISSING
    speed: ScopeFloat = MISSING
    block_top: ScopeBool = MISSING
    block_bottom: ScopeBool = MISSING
    block_scroll: ScopeBool = MISSING
    block_reverse: ScopeBool = MISSING
    block_fixed: ScopeBool = MISSING
    block_special: ScopeBool = MISSING
    block_colorful: ScopeBool = MISSING
    block_keyword_patterns: tuple[str, ...] | None | _Missing = MISSING

    def __post_init__(self) -> None:
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


@dataclass(frozen=True, slots=True, init=False)
class ResolvedConfig:
    """扁平的 canonical 配置对象。

    对象只保存 9 个 Spec，不保存 parent，也不在字段访问时做继承解析。
    兼容入口可以在构造时传入 ``parent``，但它只会被立即展开并合并一次；
    构造完成后不会保留任何作用域链。
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
        parent: ResolvedConfig | None = None,
        **overrides: Any,
    ) -> None:
        supplied = dict(parent.values) if parent is not None else {}
        supplied.update(values or {})
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
        if isinstance(value, dict):
            unknown = value.keys() - _SPEC_FIELDS[section]
            if unknown:
                names = ", ".join(sorted(unknown))
                raise TypeError(f"unknown {section} fields: {names}")
            return spec_type(**value)
        raise TypeError(f"{section} must be {spec_type.__name__} or a field mapping")

    @property
    def values(self) -> Mapping[str, Any]:
        """返回对象当前已经拥有的 canonical ``spec.field`` 值。"""
        result: dict[str, Any] = {}
        for section in _SPEC_TYPES:
            spec = getattr(self, section)
            for descriptor in fields(spec):
                value = getattr(spec, descriptor.name)
                if value is not MISSING:
                    result[f"{section}.{descriptor.name}"] = value
        return MappingProxyType(result)

    def flatten(self, *, stop_at: ResolvedConfig | None = None) -> dict[str, Any]:
        """兼容旧调用；配置已经是扁平的，因此这里只复制当前值。"""
        if self is stop_at:
            return {}
        return dict(self.values)


def merge_configs(*configs: ResolvedConfig) -> ResolvedConfig:
    """按从低到高的优先级立即合并多个配置对象。"""
    values: dict[str, Any] = {}
    for config in configs:
        values.update(config.values)
    return ResolvedConfig(values)


_DEFAULT_VALUES: dict[str, Any] = {
    "selection.expression": None,
    "selection.with_extra_episodes": False,
    "selection.skip_preview": False,
    "selection.published_since": None,
    "selection.published_before": None,
    "runtime.jobs": 1,
    "runtime.ffmpeg_path": None,
    "runtime.preview_formats": False,
    "runtime.no_color": False,
    "runtime.no_progress": False,
    "runtime.debug": False,
    "auth.cookie": "",
    "auth.file": None,
    "auth.profile": "default",
    "auth.sessdata": "",
    "auth.login_strict": False,
    "auth.vip_strict": False,
    "auth.mode": "terminal",
    "auth.poll_interval": 2.0,
    "auth.timeout": 180,
    "resource.video": True,
    "resource.audio": True,
    "resource.danmaku": True,
    "resource.subtitle": True,
    "resource.metadata": False,
    "resource.cover": True,
    "resource.chapter_info": True,
    "resource.save_cover": False,
    "resource.ai_translation_language": None,
    "stream.video_quality": 127,
    "stream.audio_quality": 30251,
    "stream.video_codec": "avc:copy",
    "stream.audio_codec": "mp4a:copy",
    "stream.video_codec_priority": None,
    "output.format": "infer",
    "output.audio_only_format": "infer",
    "output.directory": Path(),
    "output.temporary_directory": None,
    "output.overwrite": False,
    "output.subpath_template": "{auto}",
    "output.metadata_premiered_format": "%Y-%m-%d",
    "network.proxy": "auto",
    "network.fetch_workers": 8,
    "network.download_workers": 8,
    "network.block_size": 0.5,
    "network.download_interval": 0,
    "network.banned_mirrors_pattern": None,
    "danmaku.format": "ass",
    "danmaku.font_size": None,
    "danmaku.font": "SimHei",
    "danmaku.opacity": 0.8,
    "danmaku.display_region_ratio": 1.0,
    "danmaku.speed": 1.0,
    "danmaku.block_top": False,
    "danmaku.block_bottom": False,
    "danmaku.block_scroll": False,
    "danmaku.block_reverse": False,
    "danmaku.block_fixed": False,
    "danmaku.block_special": False,
    "danmaku.block_colorful": False,
    "danmaku.block_keyword_patterns": None,
}

DEFAULT_CONFIG = ResolvedConfig(_DEFAULT_VALUES)

# 迁移期兼容名：不再存在 Scope 类型或 ROOT_SCOPE 的 parent chain。
Scope: TypeAlias = ResolvedConfig
ROOT_SCOPE = DEFAULT_CONFIG


__all__ = [
    "AuthSpec",
    "DEFAULT_CONFIG",
    "DanmakuSpec",
    "MISSING",
    "NetworkSpec",
    "OutputSpec",
    "ResolvedConfig",
    "ResourceSpec",
    "ROOT_SCOPE",
    "RuntimeSpec",
    "Scope",
    "SelectionSpec",
    "SourceSpec",
    "StreamSpec",
    "merge_configs",
]
