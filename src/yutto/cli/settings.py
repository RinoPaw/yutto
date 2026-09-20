from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from yutto.media.quality import AudioQuality, VideoQuality
from yutto.utils.console.logger import Logger
from yutto.utils.paths import user_config_home


class _ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class YuttoBasicConfig(_ConfigModel):
    """Persistent configuration overrides for basic download and CLI behavior."""

    num_workers: int | None = Field(default=None, gt=0)
    jobs: int | None = Field(default=None, gt=0)
    fetch_workers: int | None = Field(default=None, gt=0)
    video_quality: VideoQuality | None = None
    audio_quality: AudioQuality | None = None
    vcodec: str | None = None
    acodec: str | None = None
    download_vcodec_priority: list[str] | None = None
    output_format: Literal["infer", "mp4", "mkv", "mov"] | None = None
    output_format_audio_only: Literal["infer", "m4a", "aac", "mp3", "flac", "mp4", "mkv", "mov"] | None = None
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
    metadata_format_premiered: str | None = None
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

    font_size: int | None = None
    font: str | None = None
    opacity: float | None = None
    display_region_ratio: float | None = None
    speed: float | None = None
    block_top: bool | None = None
    block_bottom: bool | None = None
    block_scroll: bool | None = None
    block_reverse: bool | None = None
    block_fixed: bool | None = None
    block_special: bool | None = None
    block_colorful: bool | None = None
    block_keyword_patterns: list[str] | None = None


class YuttoBatchConfig(_ConfigModel):
    """Persistent batch-selection overrides."""

    with_extra_episodes: bool | None = None
    skip_preview: bool | None = None
    batch_filter_start_time: str | None = None
    batch_filter_end_time: str | None = None


class YuttoAuthConfig(_ConfigModel):
    """Persistent credential-source overrides."""

    auth: str | None = None
    auth_file: str | None = None
    auth_profile: str | None = None


class YuttoConfig(_ConfigModel):
    """Values explicitly supplied by persistent configuration.

    Application defaults live in their owning core or frontend models. An empty
    config object therefore contributes no overrides.
    """

    basic: YuttoBasicConfig = Field(default_factory=YuttoBasicConfig)
    resource: YuttoResourceConfig = Field(default_factory=YuttoResourceConfig)
    danmaku: YuttoDanmakuConfig = Field(default_factory=YuttoDanmakuConfig)
    batch: YuttoBatchConfig = Field(default_factory=YuttoBatchConfig)
    auth: YuttoAuthConfig = Field(default_factory=YuttoAuthConfig)


def search_for_settings_file() -> Path | None:
    settings_file = Path("yutto.toml")
    # 此时还没有设置 debug，所以 Logger.debug 永远不会输出
    if not settings_file.exists():
        Logger.debug("Settings file not found in current directory.")
        settings_file = user_config_home() / "yutto" / "yutto.toml"
    if not settings_file.exists():
        Logger.debug(f"Settings file not found in user config home ({settings_file}).")
        return None
    Logger.debug(f"Settings file found at {settings_file}.")
    return settings_file


def load_settings_file(settings_file: Path) -> YuttoConfig:
    with settings_file.open("r", encoding="utf-8") as f:
        settings_raw: Any = tomllib.loads(f.read())
    return YuttoConfig.model_validate(settings_raw)


if __name__ == "__main__":
    settings_file = search_for_settings_file()
    assert settings_file is not None
    settings = load_settings_file(settings_file)
    print(settings.model_dump())
