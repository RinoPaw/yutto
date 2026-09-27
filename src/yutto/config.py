from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
class CredentialSpec:
    """一次任务使用的认证来源与 profile 选择。"""

    cookie: str = ""
    file: Path | None = None
    profile: str = "default"
    sessdata: str = ""


@dataclass(frozen=True, slots=True)
class AccessSpec:
    """一次任务对登录状态与会员权限的要求。"""

    login_strict: bool = False
    vip_strict: bool = False


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


@dataclass(frozen=True, slots=True)
class NetworkSpec:
    """网络访问、传输并发与下载节奏。"""

    proxy: str = "auto"
    fetch_workers: int = 8
    download_workers: int = 8
    block_size: float = 0.5
    download_interval: int = 0
    banned_mirrors_pattern: str | None = None


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


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """一次下载/解析任务已经归一化的完整 typed config。"""

    source: SourceSpec = field(default_factory=SourceSpec)
    selection: SelectionSpec = field(default_factory=SelectionSpec)
    credential: CredentialSpec = field(default_factory=CredentialSpec)
    access: AccessSpec = field(default_factory=AccessSpec)
    resource: ResourceSpec = field(default_factory=ResourceSpec)
    stream: StreamSpec = field(default_factory=StreamSpec)
    output: OutputSpec = field(default_factory=OutputSpec)
    network: NetworkSpec = field(default_factory=NetworkSpec)
    danmaku: DanmakuSpec = field(default_factory=DanmakuSpec)


DEFAULT_CONFIG = ResolvedConfig()


__all__ = [
    "AccessSpec",
    "CredentialSpec",
    "DEFAULT_CONFIG",
    "DanmakuSpec",
    "NetworkSpec",
    "OutputSpec",
    "ResolvedConfig",
    "ResourceSpec",
    "SelectionSpec",
    "SourceSpec",
    "StreamSpec",
]
