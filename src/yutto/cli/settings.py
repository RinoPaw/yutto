from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from yutto.config import DEFAULT_CONFIG, ResolvedConfig
from yutto.media.quality import AudioQuality, VideoQuality
from yutto.output_formats import AudioOnlyOutputFormat, OutputFormat
from yutto.utils.console.logger import Logger
from yutto.utils.paths import user_config_home
from yutto.utils.time import parse_local_timestamp

if TYPE_CHECKING:
    from collections.abc import Callable


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
    """Values explicitly supplied by persistent configuration."""

    basic: YuttoBasicConfig = Field(default_factory=YuttoBasicConfig)
    resource: YuttoResourceConfig = Field(default_factory=YuttoResourceConfig)
    danmaku: YuttoDanmakuConfig = Field(default_factory=YuttoDanmakuConfig)
    batch: YuttoBatchConfig = Field(default_factory=YuttoBatchConfig)
    auth: YuttoAuthConfig = Field(default_factory=YuttoAuthConfig)


_BASIC_NON_TASK_FIELDS = frozenset({"aliases", "jobs", "ffmpeg_path", "no_color", "no_progress", "debug"})


def resolved_config_from_settings(config: YuttoConfig) -> ResolvedConfig:
    """Resolve persistent task settings directly into typed Specs."""
    basic = config.basic

    network_updates = _present_updates(
        basic,
        {
            "download_workers": "download_workers",
            "fetch_workers": "fetch_workers",
            "block_size": "block_size",
            "proxy": "proxy",
            "download_interval": "download_interval",
            "banned_mirrors_pattern": "banned_mirrors_pattern",
        },
    )
    stream_updates = _present_updates(
        basic,
        {
            "video_quality": "video_quality",
            "audio_quality": "audio_quality",
            "vcodec": "video_codec",
            "acodec": "audio_codec",
        },
    )
    if "download_vcodec_priority" in basic.model_fields_set:
        priority = basic.download_vcodec_priority
        stream_updates["video_codec_priority"] = None if priority is None else tuple(priority)

    output_updates = _present_updates(
        basic,
        {
            "output_format": "format",
            "output_format_audio_only": "audio_only_format",
            "overwrite": "overwrite",
            "subpath_template": "subpath_template",
            "metadata_premiered_format": "metadata_premiered_format",
        },
    )
    if "dir" in basic.model_fields_set:
        output_updates["directory"] = Path(basic.dir).expanduser() if basic.dir is not None else Path()
    if "tmp_dir" in basic.model_fields_set:
        output_updates["temporary_directory"] = None if basic.tmp_dir is None else Path(basic.tmp_dir).expanduser()

    credential_updates = _present_updates(basic, {"sessdata": "sessdata"})
    credential_updates.update(
        _present_updates(
            config.auth,
            {
                "auth": "cookie",
                "auth_profile": "profile",
            },
        )
    )
    if "auth_file" in config.auth.model_fields_set:
        credential_updates["file"] = (
            None if config.auth.auth_file is None else Path(config.auth.auth_file).expanduser()
        )

    access_updates = _present_updates(
        basic,
        {
            "login_strict": "login_strict",
            "vip_strict": "vip_strict",
        },
    )

    resource_updates = _present_updates(
        config.resource,
        {
            "require_video": "video",
            "require_audio": "audio",
            "require_danmaku": "danmaku",
            "require_subtitle": "subtitle",
            "require_metadata": "metadata",
            "require_cover": "cover",
            "require_chapter_info": "chapter_info",
            "save_cover": "save_cover",
        },
    )
    resource_updates.update(_present_updates(basic, {"ai_translation_language": "ai_translation_language"}))

    selection_updates = _present_updates(
        config.batch,
        {
            "with_extra_episodes": "with_extra_episodes",
            "skip_preview": "skip_preview",
        },
    )
    if "published_since" in config.batch.model_fields_set:
        value = config.batch.published_since
        selection_updates["published_since"] = None if value is None else parse_local_timestamp(value)
    if "published_before" in config.batch.model_fields_set:
        value = config.batch.published_before
        selection_updates["published_before"] = None if value is None else parse_local_timestamp(value)

    danmaku_updates = _present_updates(
        config.danmaku,
        {
            "danmaku_font_size": "font_size",
            "danmaku_font": "font",
            "danmaku_opacity": "opacity",
            "danmaku_display_region_ratio": "display_region_ratio",
            "danmaku_speed": "speed",
            "danmaku_block_top": "block_top",
            "danmaku_block_bottom": "block_bottom",
            "danmaku_block_scroll": "block_scroll",
            "danmaku_block_reverse": "block_reverse",
            "danmaku_block_fixed": "block_fixed",
            "danmaku_block_special": "block_special",
            "danmaku_block_colorful": "block_colorful",
        },
    )
    if "danmaku_block_keyword_patterns" in config.danmaku.model_fields_set:
        patterns = config.danmaku.danmaku_block_keyword_patterns
        danmaku_updates["block_keyword_patterns"] = None if patterns is None else tuple(patterns)
    if "danmaku_format" in basic.model_fields_set:
        danmaku_updates["format"] = basic.danmaku_format

    task_fields = basic.model_fields_set - _BASIC_NON_TASK_FIELDS
    handled_basic_fields = {
        "download_workers",
        "fetch_workers",
        "video_quality",
        "audio_quality",
        "vcodec",
        "acodec",
        "download_vcodec_priority",
        "output_format",
        "output_format_audio_only",
        "ai_translation_language",
        "danmaku_format",
        "block_size",
        "overwrite",
        "proxy",
        "dir",
        "tmp_dir",
        "sessdata",
        "subpath_template",
        "metadata_premiered_format",
        "download_interval",
        "banned_mirrors_pattern",
        "vip_strict",
        "login_strict",
    }
    unknown = task_fields - handled_basic_fields
    if unknown:
        raise TypeError(f"config fields without task mapping: {', '.join(sorted(unknown))}")

    return replace(
        DEFAULT_CONFIG,
        selection=replace(DEFAULT_CONFIG.selection, **selection_updates),
        credential=replace(DEFAULT_CONFIG.credential, **credential_updates),
        access=replace(DEFAULT_CONFIG.access, **access_updates),
        resource=replace(DEFAULT_CONFIG.resource, **resource_updates),
        stream=replace(DEFAULT_CONFIG.stream, **stream_updates),
        output=replace(DEFAULT_CONFIG.output, **output_updates),
        network=replace(DEFAULT_CONFIG.network, **network_updates),
        danmaku=replace(DEFAULT_CONFIG.danmaku, **danmaku_updates),
    )


def _present_updates(model: BaseModel, fields: dict[str, str]) -> dict[str, Any]:
    return {
        target: getattr(model, source)
        for source, target in fields.items()
        if source in model.model_fields_set
    }


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
