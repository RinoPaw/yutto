from __future__ import annotations

from dataclasses import dataclass, fields
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


@dataclass(frozen=True, slots=True, init=False)
class Scope:
    """一层 yutto 参数作用域。

    Scope 统一承载 yutto 的参数状态，并按生命周期分成三类：

    1. 运行前参数：启动实际执行前即可由 CLI、配置文件、环境或上级 Scope 确定的输入、偏好和策略。
    2. 运行时解析值：必须读取环境、文件、网络响应或探测外部程序后才能确定，但确定后仍可作为参数继续传递的值。
    3. 运行时资源 / 状态：只在执行期间存在的对象或可变状态，例如 session、limiter、cache、lock 等。

    Scope 字段名是 yutto 参数的权威命名。外部来源必须在创建 Scope 前完成解析和命名转换。
    ``MISSING`` 表示当前层没有定义该字段；``None`` / ``False`` 等显式值会正常遮蔽父作用域。
    """

    # 当前层找不到参数时继续查询的父作用域。
    parent: Scope | None = None

    # =====================================================================
    # 运行前参数
    # =====================================================================
    # 这些值在真正访问网络、读取认证文件、探测 FFmpeg 或创建执行资源之前即可确定。
    # ``auto`` / ``infer`` / ``None`` 等仍属于运行前策略；它们描述“运行时如何解析”，
    # 而不是解析后的最终结果。

    # ----- 下载调用 -----
    # 用户提供的下载源：Bilibili URL、ID、别名、文件路径或 file:// URL。
    source: ScopeText = MISSING
    # 分集/条目选择表达式。
    selection_expr: ScopeText = MISSING
    # 是否只预览可用媒体格式并退出。
    preview_formats: ScopeBool = MISSING

    # ----- 基础下载 -----
    # 单个下载任务同时工作的最大媒体下载 Worker 数。
    download_workers: ScopeInt = MISSING
    # 同时执行的下载任务数量。
    jobs: ScopeInt = MISSING
    # 批量解析阶段同时发起请求的最大 Worker 数。
    fetch_workers: ScopeInt = MISSING
    # 期望的视频清晰度代码；实际可用清晰度需要运行时解析媒体信息。
    video_quality: ScopeInt = MISSING
    # 期望的音频质量/码率代码；实际可用质量需要运行时解析媒体信息。
    audio_quality: ScopeInt = MISSING
    # 视频下载编码与保存编码策略。
    vcodec: ScopeText = MISSING
    # 音频下载编码与保存编码策略。
    acodec: ScopeText = MISSING
    # 视频下载编码优先级；显式 None 表示运行时自动推断。
    download_vcodec_priority: list[str] | None | _Missing = MISSING
    # 普通视频输出封装策略；infer 表示运行时自动推断。
    output_format: ScopeText = MISSING
    # 仅含音频流时的输出封装策略；infer 表示运行时自动推断。
    output_format_audio_only: ScopeText = MISSING
    # FFmpeg 可执行文件路径；实际存在性与能力需要运行时探测。
    ffmpeg_path: ScopeText = MISSING
    # AI 原声翻译的目标语言。
    ai_translation_language: ScopeText = MISSING
    # 弹幕输出格式：xml / ass / protobuf。
    danmaku_format: ScopeText = MISSING
    # 分块下载时单个块大小，单位 MiB。
    block_size: ScopeFloat = MISSING
    # 是否覆盖已经存在的输出文件。
    overwrite: ScopeBool = MISSING
    # 代理策略或代理 URL；auto 的最终代理需要运行时环境解析。
    proxy: ScopeText = MISSING
    # 下载输出目录。
    dir: ScopePath = MISSING
    # 下载中间文件使用的临时目录。
    tmp_dir: ScopePath = MISSING
    # 旧版兼容的内联 SESSDATA 输入。
    sessdata: ScopeText = MISSING
    # 构造多级输出目录时使用的路径模板。
    subpath_template: ScopeText = MISSING
    # 用户自定义别名到 URL 的映射。
    aliases: dict[str, str] | None | _Missing = MISSING
    # metadata 中 premiered 字段的日期格式。
    metadata_premiered_format: ScopeText = MISSING
    # 相邻下载之间的等待时间，单位秒。
    download_interval: ScopeInt = MISSING
    # 用来排除 CDN/镜像下载地址的正则表达式。
    banned_mirrors_pattern: ScopeText = MISSING
    # 是否严格要求运行时验证大会员状态有效。
    vip_strict: ScopeBool = MISSING
    # 是否严格要求运行时验证登录状态有效。
    login_strict: ScopeBool = MISSING
    # 是否关闭彩色 ANSI 输出。
    no_color: ScopeBool = MISSING
    # 是否关闭进度条/状态栏。
    no_progress: ScopeBool = MISSING
    # 是否启用 debug 日志和 tracing。
    debug: ScopeBool = MISSING

    # ----- 认证 -----
    # 内联 Cookie，例如 SESSDATA=...; bili_jct=...。
    auth: ScopeText = MISSING
    # 认证信息读取/写入的文件路径。
    auth_file: ScopePath = MISSING
    # 认证文件中的 profile 名称。
    auth_profile: ScopeText = MISSING
    # 登录二维码展示方式：terminal / web。
    mode: ScopeText = MISSING
    # 扫码登录轮询间隔，单位秒。
    poll_interval: ScopeFloat = MISSING
    # 扫码登录超时时间，单位秒。
    timeout: ScopeInt = MISSING

    # ----- 资源选择 -----
    # 下载结果是否要求视频流。
    require_video: ScopeBool = MISSING
    # 下载结果是否要求音频流。
    require_audio: ScopeBool = MISSING
    # 是否要求生成弹幕文件。
    require_danmaku: ScopeBool = MISSING
    # 是否要求生成字幕文件。
    require_subtitle: ScopeBool = MISSING
    # 是否要求生成 metadata 文件。
    require_metadata: ScopeBool = MISSING
    # 是否要求生成/处理封面。
    require_cover: ScopeBool = MISSING
    # 是否要求封装/生成章节信息。
    require_chapter_info: ScopeBool = MISSING
    # 是否额外保存独立封面文件。
    save_cover: ScopeBool = MISSING

    # ----- 弹幕 -----
    # 弹幕字体大小。
    danmaku_font_size: ScopeInt = MISSING
    # 弹幕字体名称。
    danmaku_font: ScopeText = MISSING
    # 弹幕不透明度。
    danmaku_opacity: ScopeFloat = MISSING
    # 弹幕显示区域占视频高度的比例。
    danmaku_display_region_ratio: ScopeFloat = MISSING
    # 弹幕滚动速度。
    danmaku_speed: ScopeFloat = MISSING
    # 是否屏蔽顶部弹幕。
    danmaku_block_top: ScopeBool = MISSING
    # 是否屏蔽底部弹幕。
    danmaku_block_bottom: ScopeBool = MISSING
    # 是否屏蔽普通滚动弹幕。
    danmaku_block_scroll: ScopeBool = MISSING
    # 是否屏蔽逆向滚动弹幕。
    danmaku_block_reverse: ScopeBool = MISSING
    # 是否屏蔽固定位置弹幕。
    danmaku_block_fixed: ScopeBool = MISSING
    # 是否屏蔽高级/特殊弹幕。
    danmaku_block_special: ScopeBool = MISSING
    # 是否屏蔽彩色弹幕。
    danmaku_block_colorful: ScopeBool = MISSING
    # 用于过滤弹幕文本的关键词/正则列表。
    danmaku_block_keyword_patterns: list[str] | None | _Missing = MISSING

    # ----- 内容筛选 -----
    # 是否包含 PV、预告、特别篇等附加内容。
    with_extra_episodes: ScopeBool = MISSING
    # 是否跳过预告片。
    skip_preview: ScopeBool = MISSING
    # 只选择该时间及之后发布的内容。
    published_since: ScopeText = MISSING
    # 只选择该时间之前发布的内容。
    published_before: ScopeText = MISSING

    # ----- Server -----
    # JSON-RPC server 监听地址。
    host: ScopeText = MISSING
    # JSON-RPC server 监听端口。
    port: ScopeInt = MISSING
    # 允许访问 server 的浏览器 Origin 列表。
    allow_origin: list[str] | tuple[str, ...] | None | _Missing = MISSING
    # server token 文件路径。
    token_file: ScopePath = MISSING
    # RPC 下载允许写入的根目录。
    download_root: ScopePath = MISSING
    # RPC 临时文件允许写入的根目录。
    tmp_root: ScopePath = MISSING
    # 单个 server 任务允许的最大解析并发数。
    max_fetch_workers: ScopeInt = MISSING
    # 单个 server 任务允许的最大下载并发数。
    max_download_workers: ScopeInt = MISSING
    # server 保留的运行中、排队中和历史任务总数上限。
    task_limit: ScopeInt = MISSING

    # =====================================================================
    # 运行时解析值
    # =====================================================================
    # 这类值必须实际读取环境、文件、网络响应或探测外部程序后才能确定。
    # 它们仍是已经解析完成、可以继续向下传递的值，不是执行资源本身。

    # ----- Server -----
    # 实际使用的 server token；可能来自环境变量、token 文件或运行时随机生成。
    server_token: ScopeText = MISSING

    # =====================================================================
    # 运行时资源 / 状态
    # =====================================================================
    # 这类值只在执行期间存在，并且通常具有生命周期或可变状态，例如：
    # session、fetch_limiter、nav_cache、nav_lock、touched_urls。
    # 当前尚未把这些执行资源迁入本 Scope；这里先明确分类边界，后续字段应放在本区。

    def __init__(self, values: Mapping[str, Any] | None = None, parent: Scope | None = None, **overrides: Any) -> None:
        object.__setattr__(self, "parent", parent)

        known_fields = {descriptor.name for descriptor in fields(type(self)) if descriptor.name != "parent"}
        for name in known_fields:
            object.__setattr__(self, name, MISSING)

        supplied = dict(values or {})
        supplied.update(overrides)
        unknown = supplied.keys() - known_fields
        if unknown:
            names = ", ".join(sorted(unknown))
            raise TypeError(f"unknown Scope fields: {names}")

        for name, value in supplied.items():
            object.__setattr__(self, name, value)

    @property
    def values(self) -> Mapping[str, Any]:
        """返回当前层显式定义的字段，不包含父作用域。"""
        return MappingProxyType(
            {
                descriptor.name: getattr(self, descriptor.name)
                for descriptor in fields(type(self))
                if descriptor.name != "parent" and getattr(self, descriptor.name) is not MISSING
            }
        )

    def lookup(self, key: str) -> Any:
        """从当前层开始解析字段；所有层都未定义时返回 ``MISSING``。"""
        if key not in {descriptor.name for descriptor in fields(type(self)) if descriptor.name != "parent"}:
            raise KeyError(f"unknown Scope field: {key}")

        value = getattr(self, key)
        if value is not MISSING:
            return value
        if self.parent is not None:
            return self.parent.lookup(key)
        return MISSING

    def flatten(self, *, stop_at: Scope | None = None) -> dict[str, Any]:
        """按父到子的顺序展开作用域链，子作用域覆盖父作用域。"""
        if self is stop_at:
            return {}
        values = self.parent.flatten(stop_at=stop_at) if self.parent is not None else {}
        values.update(self.values)
        return values
