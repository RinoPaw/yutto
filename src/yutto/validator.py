from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import biliass

from yutto.auth import format_auth_inline, resolve_auth
from yutto.core.execution import (
    resolve_download_workers,
    resolve_fetch_workers,
    resolve_network_proxy,
)
from yutto.downloader.planner import resolve_block_size_bytes
from yutto.output_formats import resolve_audio_only_output_format, resolve_output_format
from yutto.resource import resolve_danmaku_format, should_save_cover
from yutto.stream import (
    resolve_audio_codecs,
    resolve_audio_quality,
    resolve_video_codec_priority,
    resolve_video_codecs,
    resolve_video_quality,
    video_codec_priority_default,
)
from yutto.utils.console.colorful import set_no_color
from yutto.utils.console.logger import Logger, set_logger_debug
from yutto.utils.fetcher import resolve_proxy

if TYPE_CHECKING:
    import argparse

    from yutto.auth import AuthInfo
    from yutto.scope import ResolvedConfig
    from yutto.utils.ffmpeg import FFmpeg


def configure_cli(*, no_progress: bool, no_color: bool, debug: bool) -> None:
    if not no_progress and sys.stdout.isatty():
        Logger.enable_statusbar()
    if no_color or os.environ.get("NO_COLOR"):
        set_no_color()
    if debug:
        set_logger_debug()
        biliass.enable_tracing()


def resolve_credentials(options: argparse.Namespace) -> AuthInfo | None:
    if not options.auth and options.sessdata:
        Logger.deprecated_warning('参数 --sessdata 已弃用，推荐改用 --auth="SESSDATA=...; bili_jct=..."')
        options.auth = format_auth_inline(options.sessdata)
    return resolve_auth(options)


def validate_download_config(config: ResolvedConfig, ffmpeg: FFmpeg) -> None:
    resolve_proxy(resolve_network_proxy(config))
    resolve_fetch_workers(config)
    resolve_download_workers(config)
    resolve_block_size_bytes(config)
    should_save_cover(config)
    resolve_danmaku_format(config)
    resolve_video_quality(config)
    resolve_audio_quality(config)
    resolve_output_format(config.output.format)
    resolve_audio_only_output_format(config.output.audio_only_format)

    video_download_codec, video_save_codec = resolve_video_codecs(config)
    _, audio_save_codec = resolve_audio_codecs(config)
    priority = resolve_video_codec_priority(config)
    if priority is not None:
        if len(priority) < len(video_codec_priority_default):
            Logger.warning(
                "download_vcodec_priority（{}）不包含所有下载视频编码（{}），不包含部分将永远不会选择哦".format(
                    ", ".join(priority), ", ".join(video_codec_priority_default)
                )
            )
        if priority[0] != video_download_codec:
            Logger.warning(
                f"download_vcodec 参数值（{video_download_codec}）不是优先级最高的编码（{priority[0]}），可能会导致下载失败哦"
            )

    if video_save_codec not in ffmpeg.video_encodecs + ["copy"]:
        raise ValueError(
            "save_vcodec 参数值（{}）不满足要求哦（允许值：{{{}}}）".format(
                video_save_codec, ", ".join(ffmpeg.video_encodecs + ["copy"])
            )
        )
    if audio_save_codec not in ffmpeg.audio_encodecs + ["copy"]:
        raise ValueError(
            "save_acodec 参数值（{}）不满足要求哦（允许值：{{{}}}）".format(
                audio_save_codec, ", ".join(ffmpeg.audio_encodecs + ["copy"])
            )
        )


def validate_download_scope(config: ResolvedConfig, ffmpeg: FFmpeg) -> None:
    """Compatibility wrapper for validate_download_config."""
    validate_download_config(config, ffmpeg)
