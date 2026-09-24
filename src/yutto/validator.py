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
    from yutto.scope import Scope
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


def validate_download_scope(scope: Scope, ffmpeg: FFmpeg) -> None:
    resolve_proxy(resolve_network_proxy(scope))
    resolve_fetch_workers(scope)
    resolve_download_workers(scope)
    resolve_block_size_bytes(scope)
    should_save_cover(scope)
    resolve_danmaku_format(scope)
    resolve_video_quality(scope)
    resolve_audio_quality(scope)
    resolve_output_format(scope.output.format)
    resolve_audio_only_output_format(scope.output.audio_only_format)

    video_download_codec, video_save_codec = resolve_video_codecs(scope)
    _, audio_save_codec = resolve_audio_codecs(scope)
    priority = resolve_video_codec_priority(scope)
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
