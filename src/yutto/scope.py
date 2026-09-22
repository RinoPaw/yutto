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

    # 用户提供的下载源：Bilibili URL、ID、文件路径或 file:// URL。
    value: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class SelectionSpec:
    """一个下载源内部的内容选择规则。"""

    # 分集/条目选择表达式。
    expression: ScopeText = MISSING
    # 是否包含 PV、预告、特别篇等附加内容。
    with_extra_episodes: ScopeBool = MISSING
    # 是否跳过预告片。
    skip_preview: ScopeBool = MISSING
    # 只选择该时间及之后发布的内容。
    published_since: ScopeText = MISSING
    # 只选择该时间之前发布的内容。
    published_before: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    """一次 yutto 调用自身的运行策略。"""

    # 同时执行的下载任务数量。
    jobs: ScopeInt = MISSING
    # FFmpeg 可执行文件路径。
    ffmpeg_path: ScopeText = MISSING
    # 是否只预览可用媒体格式并退出。
    preview_formats: ScopeBool = MISSING
    # 是否关闭彩色 ANSI 输出。
    no_color: ScopeBool = MISSING
    # 是否关闭进度条/状态栏。
    no_progress: ScopeBool = MISSING
    # 是否启用 debug 日志和 tracing。
    debug: ScopeBool = MISSING


@dataclass(frozen=True, slots=True)
class AuthSpec:
    """认证来源、访问校验以及 auth 命令参数。"""

    # 内联 Cookie，例如 SESSDATA=...; bili_jct=...。
    cookie: ScopeText = MISSING
    # 认证信息读取/写入的文件路径。
    file: ScopePath = MISSING
    # 认证文件中的 profile 名称。
    profile: ScopeText = MISSING
    # 旧版兼容的内联 SESSDATA 输入。
    sessdata: ScopeText = MISSING
    # 是否严格要求登录状态有效。
    login_strict: ScopeBool = MISSING
    # 是否严格要求大会员状态有效。
    vip_strict: ScopeBool = MISSING
    # 登录二维码展示方式：terminal / web。
    mode: ScopeText = MISSING
    # 扫码登录轮询间隔，单位秒。
    poll_interval: ScopeFloat = MISSING
    # 扫码登录超时时间，单位秒。
    timeout: ScopeInt = MISSING


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """下载产物中需要获取、处理或保留的资源。"""

    # 是否要求视频流。
    video: ScopeBool = MISSING
    # 是否要求音频流。
    audio: ScopeBool = MISSING
    # 是否要求生成弹幕文件。
    danmaku: ScopeBool = MISSING
    # 是否要求生成字幕文件。
    subtitle: ScopeBool = MISSING
    # 是否要求生成 metadata 文件。
    metadata: ScopeBool = MISSING
    # 是否要求生成/处理封面。
    cover: ScopeBool = MISSING
    # 是否要求封装/生成章节信息。
    chapter_info: ScopeBool = MISSING
    # 是否额外保存独立封面文件。
    save_cover: ScopeBool = MISSING
    # AI 原声翻译的目标语言。
    ai_translation_language: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class StreamSpec:
    """音视频流质量与编码偏好。"""

    # 期望的视频清晰度代码。
    video_quality: ScopeInt = MISSING
    # 期望的音频质量/码率代码。
    audio_quality: ScopeInt = MISSING
    # 视频下载编码与保存编码策略，格式为 DOWNLOAD:SAVE。
    video_codec: ScopeText = MISSING
    # 音频下载编码与保存编码策略，格式为 DOWNLOAD:SAVE。
    audio_codec: ScopeText = MISSING
    # 视频下载编码优先级；显式 None 表示自动推断。
    video_codec_priority: list[str] | None | _Missing = MISSING


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """输出目录、封装格式与命名策略。"""

    # 普通视频输出封装策略；infer 表示自动推断。
    format: ScopeText = MISSING
    # 仅含音频流时的输出封装策略；infer 表示自动推断。
    audio_only_format: ScopeText = MISSING
    # 下载输出目录。
    directory: ScopePath = MISSING
    # 下载中间文件使用的临时目录。
    temporary_directory: ScopePath = MISSING
    # 是否覆盖已经存在的输出文件。
    overwrite: ScopeBool = MISSING
    # 构造多级输出目录时使用的路径模板。
    subpath_template: ScopeText = MISSING
    # metadata 中 premiered 字段的日期格式。
    metadata_premiered_format: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class NetworkSpec:
    """网络访问、传输并发与下载节奏。"""

    # 代理策略或显式代理 URL：auto / no / URL。
    proxy: ScopeText = MISSING
    # 批量解析阶段同时发起请求的最大 Worker 数。
    fetch_workers: ScopeInt = MISSING
    # 单个下载任务同时工作的最大媒体下载 Worker 数。
    download_workers: ScopeInt = MISSING
    # 分块下载时单个块大小，单位 MiB。
    block_size: ScopeFloat = MISSING
    # 相邻下载之间的等待时间，单位秒。
    download_interval: ScopeInt = MISSING
    # 用来排除 CDN/镜像下载地址的正则表达式。
    banned_mirrors_pattern: ScopeText = MISSING


@dataclass(frozen=True, slots=True)
class DanmakuSpec:
    """弹幕序列化、渲染与过滤参数。"""

    # 弹幕输出格式：xml / ass / protobuf。
    format: ScopeText = MISSING
    # 弹幕字体大小。
    font_size: ScopeInt = MISSING
    # 弹幕字体名称。
    font: ScopeText = MISSING
    # 弹幕不透明度。
    opacity: ScopeFloat = MISSING
    # 弹幕显示区域占视频高度的比例。
    display_region_ratio: ScopeFloat = MISSING
    # 弹幕滚动速度。
    speed: ScopeFloat = MISSING
    # 是否屏蔽顶部弹幕。
    block_top: ScopeBool = MISSING
    # 是否屏蔽底部弹幕。
    block_bottom: ScopeBool = MISSING
    # 是否屏蔽普通滚动弹幕。
    block_scroll: ScopeBool = MISSING
    # 是否屏蔽逆向滚动弹幕。
    block_reverse: ScopeBool = MISSING
    # 是否屏蔽固定位置弹幕。
    block_fixed: ScopeBool = MISSING
    # 是否屏蔽高级/特殊弹幕。
    block_special: ScopeBool = MISSING
    # 是否屏蔽彩色弹幕。
    block_colorful: ScopeBool = MISSING
    # 用于过滤弹幕文本的关键词/正则列表。
    block_keyword_patterns: list[str] | None | _Missing = MISSING


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


class _SpecView:
    """把 ``scope.spec.field`` 转成一次惰性的作用域字段查询。"""

    __slots__ = ("_scope", "_section")

    def __init__(self, scope: Scope, section: str) -> None:
        self._scope = scope
        self._section = section

    def __getattr__(self, name: str) -> Any:
        if name not in _SPEC_FIELDS[self._section]:
            raise AttributeError(f"{self._section} has no field {name!r}")
        return self._scope._resolve(self._section, name)

    def __dir__(self) -> list[str]:
        return sorted({*super().__dir__(), *_SPEC_FIELDS[self._section]})


@dataclass(frozen=True, slots=True, init=False)
class Scope:
    """一层 yutto 参数作用域。

    Scope 字段名是 yutto 参数的唯一权威命名，并按 Spec 分类。
    例如 ``scope.network.proxy``、``scope.output.directory``、``scope.danmaku.font_size``。

    每个 Scope 只保存当前层显式设置的字段。访问 ``scope.spec.field`` 时只解析这个字段，
    如果当前层是 ``MISSING``，就沿 parent 链继续查找，因此子层只覆盖自己真正设置的字段。

    ``MISSING`` 表示当前层没有定义该字段；``None`` / ``False`` 等显式值会正常遮蔽父作用域。
    外部来源必须在创建 Scope 前把自己的命名转换成这里的权威路径。
    """

    parent: Scope | None
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
        parent: Scope | None = None,
        **overrides: Any,
    ) -> None:
        object.__setattr__(self, "parent", parent)
        for section, spec_type in _SPEC_TYPES.items():
            object.__setattr__(self, section, spec_type())

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
                raise TypeError(f"unknown Scope field: {name}")
            field_updates.setdefault(section, {})[field_name] = value

        for section, spec_type in _SPEC_TYPES.items():
            local = section_values.get(section, spec_type())
            updates = field_updates.get(section)
            if updates:
                local = replace(local, **updates)
            object.__setattr__(self, section, local)

    def __getattribute__(self, name: str) -> Any:
        if name in _SPEC_TYPES:
            return _SpecView(self, name)
        return object.__getattribute__(self, name)

    def _resolve(self, section: str, field_name: str) -> Any:
        local = object.__getattribute__(self, section)
        value = getattr(local, field_name)
        if value is not MISSING:
            return value

        parent = object.__getattribute__(self, "parent")
        if parent is None:
            return MISSING
        return parent._resolve(section, field_name)

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
        """返回当前层显式定义的权威字段路径，不包含父作用域。"""
        result: dict[str, Any] = {}
        for section, spec_type in _SPEC_TYPES.items():
            local = object.__getattribute__(self, section)
            for descriptor in fields(spec_type):
                value = getattr(local, descriptor.name)
                if value is not MISSING:
                    result[f"{section}.{descriptor.name}"] = value
        return MappingProxyType(result)

    def flatten(self, *, stop_at: Scope | None = None) -> dict[str, Any]:
        """按父到子的顺序展开作用域链，返回权威的 ``spec.field`` 路径。"""
        if self is stop_at:
            return {}
        values = self.parent.flatten(stop_at=stop_at) if self.parent is not None else {}
        values.update(self.values)
        return values
