from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from yutto.core.operation import ReportLevel, emit_download_report
from yutto.exceptions import PostprocessingError
from yutto.utils.ffmpeg import FFmpeg, FFmpegCommandBuilder

if TYPE_CHECKING:
    import subprocess
    from pathlib import Path
    from typing import Protocol

    from yutto.downloader.planner import DownloadPlan

    class FFmpegRunner(Protocol):
        async def exec_async(self, args: list[str]) -> subprocess.CompletedProcess[bytes]: ...


class MediaMuxer:
    """Own one FFmpeg invocation and any partial output it creates."""

    def __init__(self, ffmpeg: FFmpegRunner | None = None):
        self._ffmpeg = ffmpeg

    async def mux(
        self,
        plan: DownloadPlan,
        *,
        video_path: Path | None = None,
        audio_path: Path | None = None,
        cover_path: Path | None = None,
        has_chapter_info: bool = False,
    ) -> None:
        command_builder = FFmpegCommandBuilder()
        output = command_builder.add_output(plan.paths.output)
        emit_download_report("开始合并……")

        if plan.video is not None:
            if video_path is None:
                raise PostprocessingError("缺少已下载的视频流文件")
            video_input = command_builder.add_video_input(video_path)
            output.use(video_input)
            output.set_vcodec(plan.video_save_codec)
            if plan.attach_hvc1_tag:
                output.with_extra_options([f"-tag:v:{video_input.stream_id}", "hvc1"])

        if plan.audio is not None:
            if audio_path is None:
                raise PostprocessingError("缺少已下载的音频流文件")
            audio_input = command_builder.add_audio_input(audio_path)
            output.use(audio_input)
            output.set_acodec(plan.audio_save_codec)

        if plan.video is not None and cover_path is not None:
            cover_input = command_builder.add_video_input(cover_path)
            output.use(cover_input)
            output.set_cover(cover_input)

        if plan.video is not None and has_chapter_info:
            metadata_input = command_builder.add_metadata_input(plan.paths.chapter_info)
            output.use(metadata_input)

        output.with_extra_options(["-strict", "unofficial"])
        command_builder.with_extra_options(["-threads", str(os.cpu_count() or 1)])
        command_builder.with_extra_options(["-y"])

        ffmpeg = self._ffmpeg if self._ffmpeg is not None else FFmpeg()
        try:
            result = await ffmpeg.exec_async(command_builder.build())
        except asyncio.CancelledError:
            plan.paths.output.unlink(missing_ok=True)
            raise

        if result.returncode != 0:
            plan.paths.output.unlink(missing_ok=True)
            detail = result.stderr.decode()
            message = "合并失败！"
            if detail:
                message += f"\n{detail}"
            raise PostprocessingError(message)

        emit_download_report(result.stderr.decode(), level=ReportLevel.DEBUG)
        if not plan.paths.output.exists():
            raise PostprocessingError("合并失败：FFmpeg 未生成目标文件！")
        emit_download_report("合并完成！")
