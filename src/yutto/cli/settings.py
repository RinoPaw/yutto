from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from yutto.media.quality import AudioQuality, VideoQuality
from yutto.output_formats import AudioOnlyOutputFormat, OutputFormat
from yutto.scope import ROOT_SCOPE, Scope
from yutto.utils.console.logger import Logger
from yutto.utils.paths import user_config_home
from yutto.utils.time import parse_local_timestamp

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class _ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class YuttoBasicConfig(_ConfigModel):
    """Persistent configuration overrides for basic download and CLI behavior."""

    download_workers: int | None = Field(default=None, gt=0)
    jobs: int | None = Field(default=None, gt=0)
    fetch_workers: int | None = Field(default=None, gt=0)
    video_quality: VideoQuality | None = None
    audio_quality: AudioQuality | None = None
    vcodec: str | None = None
    acodec: str | None = None
    download_vcodec_priority: list[str] | None = None
    output_format: OutputFormat | None = None
    output_format_audio_only: AudioOnlyOutputFormat | None = None
    ffmpeg_path: str | None = None
    ai_translation_language: str | None = None
    danmaku_format: Literal["xml", "ass", "protobuf"] | None = None
    block_size: float | None = None
    overwrite: bool | None = None
    proxy: str | None = None
    dir: str | None = None
    tmp_dir: str | None = None
    sessdata: str | None = None  # legacy 兼容字段，推荐使用 [auth].auth
    subpath_template: str | None = None
    aliases: dict[str, str] | None = None
    metadata_premiered_format: str | None = None
    download_interval: int | None = None
    banned_mirrors_pattern: str | None = None
    vip_strict: bool | None = None
    login_strict: bool | None = None
    no_color: bool | None = None
    no_progress: bool | None = None
    debug: bool | None = None


class YuttoResourceConfig(_ConfigModel):
    """Persistent resource-selection overrides."""

    require_video: bool | None = None
    require_audio: bool | None = None
    require_danmaku: bool | None = None
    require_subtitle: bool | None = None
    require_metadata: bool | None = None
    require_cover: bool | None = None
    require_chapter_info: bool | None = None
    save_cover: bool | None = None


class YuttoDanmakuConfig(_ConfigModel):
    """Persistent danmaku overrides."""

    danmaku_font_size: int | None = None
    danmaku_font: str | None = None
    danmaku_opacity: float | None = None
    danmaku_display_region_ratio: float | None = None
    danmaku_speed: float | None = None
    danmaku_block_top: bool | None = None
    danmaku_block_bottom: bool | None = None
    danmaku_block_scroll: bool | None = None
    danmaku_block_reverse: bool | None = None
    danmaku_block_fixed: bool | None = None
    danmaku_block_special: bool | None = None
    danmaku_block_colorful: bool | None = None
    danmaku_block_keyword_patterns: list[str] | None = None


class YuttoBatchConfig(_ConfigModel):
    """Persistent content-selection overrides."""

    with_extra_episodes: bool | None = None
    skip_preview: bool | None = None
    published_since: str | None = None
    published_before: str | None = None


class YuttoAuthConfig(_ConfigModel):
    """Persistent credential-source overrides."""

    auth: str | None = None
    auth_file: str | None = None
    auth_profile: str | None = None


class YuttoConfig(_ConfigModel):
    """Values explicitly supplied by persistent configuration.

    Application defaults live in ``ROOT_SCOPE``. An empty config object therefore
    contributes no local overrides while still inheriting those defaults.
    """

    basic: YuttoBasicConfig = Field(default_factory=YuttoBasicConfig)
    resource: YuttoResourceConfig = Field(default_factory=YuttoResourceConfig)
    danmaku: YuttoDanmakuConfig = Field(default_factory=YuttoDanmakuConfig)
    batch: YuttoBatchConfig = Field(default_factory=YuttoBatchConfig)
    auth: YuttoAuthConfig = Field(default_factory=YuttoAuthConfig)


_BASIC_SCOPE_PATHS = {
    "download_workers": "network.download_workers",
    "jobs": "runtime.jobs",
    "fetch_workers": "network.fetch_workers",
    "video_quality": "stream.video_quality",
    "audio_quality": "stream.audio_quality",
    "vcodec": "stream.video_codec",
    "acodec": "stream.audio_codec",
    "download_vcodec_priority": "stream.video_codec_priority",
    "output_format": "output.format",
    "output_format_audio_only": "output.audio_only_format",
    "ffmpeg_path": "runtime.ffmpeg_path",
    "ai_translation_language": "resource.ai_translation_language",
    "danmaku_format": "danmaku.format",
    "block_size": "network.block_size",
    "overwrite": "output.overwrite",
    "proxy": "network.proxy",
    "dir": "output.directory",
    "tmp_dir": "output.temporary_directory",
    "sessdata": "auth.sessdata",
    "subpath_template": "output.subpath_template",
    "metadata_premiered_format": "output.metadata_premiered_format",
    "download_interval": "network.download_interval",
    "banned_mirrors_pattern": "network.banned_mirrors_pattern",
    "vip_strict": "auth.vip_strict",
    "login_strict": "auth.login_strict",
    "no_color": "runtime.no_color",
    "no_progress": "runtime.no_progress",
    "debug": "runtime.debug",
}
_RESOURCE_SCOPE_PATHS = {
    "require_video": "resource.video",
    "require_audio": "resource.audio",
    "require_danmaku": "resource.danmaku",
    "require_subtitle": "resource.subtitle",
    "require_metadata": "resource.metadata",
    "require_cover": "resource.cover",
    "require_chapter_info": "resource.chapter_info",
    "save_cover": "resource.save_cover",
}
_DANMAKU_SCOPE_PATHS = {
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
_SELECTION_SCOPE_PATHS = {
    "with_extra_episodes": "selection.with_extra_episodes",
    "skip_preview": "selection.skip_preview",
    "published_since": "selection.published_since",
    "published_before": "selection.published_before",
}
_AUTH_SCOPE_PATHS = {
    "auth": "auth.cookie",
    "auth_file": "auth.file",
    "auth_profile": "auth.profile",
}


def scope_from_config(config: YuttoConfig) -> Scope:
    """把持久配置中显式设置的值转换成一层 Scope。"""
    values: dict[str, Any] = {}
    for field_name in config.basic.model_fields_set:
        if field_name == "aliases":
            continue
        path = _BASIC_SCOPE_PATHS.get(field_name)
        if path is None:
            raise TypeError(f"config field without Scope mapping: {field_name}")
        values[path] = getattr(config.basic, field_name)

    _copy_explicit(values, config.resource, _RESOURCE_SCOPE_PATHS)
    _copy_explicit(values, config.danmaku, _DANMAKU_SCOPE_PATHS)
    _copy_explicit(values, config.batch, _SELECTION_SCOPE_PATHS)
    _copy_explicit(values, config.auth, _AUTH_SCOPE_PATHS)

    for path in ("selection.published_since", "selection.published_before"):
        value = values.get(path)
        if value is not None:
            values[path] = parse_local_timestamp(value)

    for path in ("output.directory", "output.temporary_directory", "auth.file"):
        value = values.get(path)
        if value is not None:
            values[path] = Path(value).expanduser()

    return Scope(values, parent=ROOT_SCOPE)


def _copy_explicit(target: dict[str, Any], model: BaseModel, paths: Mapping[str, str]) -> None:
    for field_name in model.model_fields_set:
        path = paths.get(field_name)
        if path is None:
            raise TypeError(f"config field without Scope mapping: {field_name}")
        target[path] = getattr(model, field_name)


def search_for_settings_file() -> Path | None:
    settings_file = Path("yutto.toml")
    # 此时还没有设置 debug，所以 Logger.debug 永远不会输出
    if not settings_file.exists():
        Logger.debug("Settings file not found in current directory.")
        settings_file = user_config_home() / "yutto" / "yutto.toml"
    if not settings_file.exists():
        Logger.debug(f"Settings file not found in user config home ({settings_file}).")
        return None
    Logger.debug(f"Settings file found in user config home ({settings_file}).")
    return settings_file


def load_settings_file(settings_file: Path) -> YuttoConfig:
    with settings_file.open("r", encoding="utf-8") as f:
        settings_raw: Any = tomllib.loads(f.read())
    return YuttoConfig.model_validate(settings_raw)


def resolve_config(
    config_path: str | Path | None = None,
    *,
    search: Callable[[], Path | None] = search_for_settings_file,
) -> YuttoConfig:
    """Resolve an explicit or discovered config file into immutable CLI settings."""
    settings_file = Path(config_path).expanduser() if config_path is not None else search()
    if settings_file is None:
        return YuttoConfig()
    Logger.info(f"发现配置文件 {settings_file}，加载中……")
    return load_settings_file(settings_file)


if __name__ == "__main__":
    settings_file = search_for_settings_file()
    assert settings_file is not None
    settings = load_settings_file(settings_file)
    print(settings.model_dump())
