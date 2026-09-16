from __future__ import annotations

import os
import sys
from dataclasses import replace
from typing import TYPE_CHECKING

import biliass

from yutto.auth import format_auth_inline, resolve_auth
from yutto.stream import audio_codec_priority_default, video_codec_priority_default
from yutto.utils.console.colorful import set_no_color
from yutto.utils.console.logger import Logger, set_logger_debug
from yutto.utils.fetcher import resolve_proxy

if TYPE_CHECKING:
    from yutto.auth import AuthInfo
    from yutto.cli.command import CredentialOptions, DownloadRuntimeOptions
    from yutto.core.request import DownloadRequest
    from yutto.utils.ffmpeg import FFmpeg


def configure_cli(command: DownloadRuntimeOptions) -> None:
    if not command.no_progress and sys.stdout.isatty():
        Logger.enable_statusbar()
    if command.no_color or os.environ.get("NO_COLOR"):
        set_no_color()
    if command.debug:
        set_logger_debug()
        biliass.enable_tracing()


def resolve_credentials(options: CredentialOptions) -> AuthInfo | None:
    if not options.auth and options.sessdata:
        Logger.deprecated_warning('参数 --sessdata 已弃用，推荐改用 --auth="SESSDATA=...; bili_jct=..."')
        options = replace(options, auth=format_auth_inline(options.sessdata))
    return resolve_auth(options)


def validate_download_request(request: DownloadRequest, ffmpeg: FFmpeg) -> None:
    resolve_proxy(request.network.proxy)

    priority = request.stream.video_download_codec_priority
    if priority is not None:
        if len(priority) < len(video_codec_priority_default):
            Logger.warning(
                "download_vcodec_priority（{}）不包含所有下载视频编码（{}），不包含部分将永远不会选择哦".format(
                    ", ".join(priority), ", ".join(video_codec_priority_default)
                )
            )
        if priority[0] != request.stream.video_download_codec:
            Logger.warning(
                f"download_vcodec 参数值（{request.stream.video_download_codec}）不是优先级最高的编码（{priority[0]}），可能会导致下载失败哦"
            )

    if request.stream.video_save_codec not in ffmpeg.video_encodecs + ["copy"]:
        raise ValueError(
            "save_vcodec 参数值（{}）不满足要求哦（允许值：{{{}}}）".format(
                request.stream.video_save_codec, ", ".join(ffmpeg.video_encodecs + ["copy"])
            )
        )
    if request.stream.audio_download_codec not in audio_codec_priority_default:
        raise ValueError(
            "download_acodec 参数值（{}）不满足要求哦（允许值：{{{}}}）".format(
                request.stream.audio_download_codec, ", ".join(audio_codec_priority_default)
            )
        )
    if request.stream.audio_save_codec not in ffmpeg.audio_encodecs + ["copy"]:
        raise ValueError(
            "save_acodec 参数值（{}）不满足要求哦（允许值：{{{}}}）".format(
                request.stream.audio_save_codec, ", ".join(ffmpeg.audio_encodecs + ["copy"])
            )
        )
