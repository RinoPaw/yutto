from __future__ import annotations

import os
import sys
from dataclasses import replace
from typing import TYPE_CHECKING

import biliass

from yutto.auth import format_auth_inline, resolve_auth
from yutto.exceptions import ErrorCode
from yutto.stream import audio_codec_priority_default, video_codec_priority_default
from yutto.utils.console.colorful import set_no_color
from yutto.utils.console.logger import Logger, set_logger_debug
from yutto.utils.fetcher import resolve_proxy
from yutto.utils.ffmpeg import FFmpeg

if TYPE_CHECKING:
    import argparse
    from typing import Any

    from yutto.auth import AuthInfo
    from yutto.cli.command import CredentialOptions, DownloadRuntimeOptions
    from yutto.core.request import DownloadRequest


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
    return resolve_auth(options)  # type: ignore[arg-type]


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


# Compatibility wrappers for callers that still pass argparse.Namespace.
def hydrate_auth(args: Any) -> AuthInfo | None:
    from pathlib import Path

    from yutto.cli.command import CredentialOptions

    options = CredentialOptions(
        auth=getattr(args, "auth", ""),
        auth_file=getattr(args, "auth_file", None),
        auth_profile=getattr(args, "auth_profile", "default"),
        sessdata=getattr(args, "sessdata", ""),
    )
    if isinstance(options.auth_file, str):
        options = replace(options, auth_file=Path(options.auth_file).expanduser())
    try:
        return resolve_credentials(options)
    except ValueError as error:
        Logger.error(str(error))
        sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)


def initial_validation(args: argparse.Namespace) -> None:
    class _Command:
        no_progress = getattr(args, "no_progress", False)
        no_color = getattr(args, "no_color", False)
        debug = getattr(args, "debug", False)

    configure_cli(_Command())  # type: ignore[arg-type]


def validate_basic_arguments(args: argparse.Namespace) -> None:
    from yutto.cli.request_adapter import download_request_from_namespace

    download_workers = getattr(args, "download_workers", getattr(args, "num_workers", 8))
    if download_workers < 1:
        Logger.error(f"num_workers 参数值（{download_workers}）不满足要求哦（应为不小于 1 的整数）")
        sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)
    fetch_workers = getattr(args, "fetch_workers", 8)
    if fetch_workers < 1:
        Logger.error(f"fetch_workers 参数值（{fetch_workers}）不满足要求哦（应为不小于 1 的整数）")
        sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)
    jobs = getattr(args, "jobs", 1)
    if jobs < 1:
        Logger.error(f"jobs 参数值（{jobs}）不满足要求哦（应为不小于 1 的整数）")
        sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)

    try:
        validate_download_request(download_request_from_namespace(args), FFmpeg())
    except ValueError as error:
        Logger.error(str(error))
        sys.exit(ErrorCode.WRONG_ARGUMENT_ERROR.value)
