from __future__ import annotations

import asyncio
import shutil
from dataclasses import replace
from typing import TYPE_CHECKING

from yutto.api.player import get_chapter_info, get_subtitle_lines
from yutto.core.events import (
    DownloadArtifactCreated,
    DownloadItemSkipped,
    DownloadMediaSelected,
    DownloadStage,
    DownloadStageChanged,
    SelectedAudioStream,
    SelectedVideoStream,
)
from yutto.core.operation import ReportLevel, emit_download_event, emit_download_report
from yutto.core.result import Artifact, ArtifactKind, ItemResult, ItemSkipReason, ItemState
from yutto.downloader.artifact_writer import ArtifactWriter
from yutto.downloader.downloaded import (
    Downloaded,
    DownloadedChapter,
    DownloadedDanmaku,
    DownloadedSubtitle,
    DownloadedSubtitleLine,
)
from yutto.downloader.media_muxer import MediaMuxer
from yutto.downloader.selector import StreamSelection
from yutto.downloader.transfer import download_files
from yutto.stream_formats import emit_manifest_formats
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.downloader.planner import DownloadPlan
    from yutto.resource import ResourceManifest
    from yutto.utils.metadata import ItemMetaData


class DownloadExecutor:
    """Execute one immutable DownloadPlan using only resources referenced by its ResourceManifest."""

    async def execute(
        self,
        scope: ExecutionScope,
        manifest: ResourceManifest,
        metadata: ItemMetaData,
        plan: DownloadPlan,
    ) -> ItemResult:
        artifact_writer = ArtifactWriter()
        try:
            plan.paths.output_dir.mkdir(parents=True, exist_ok=True)
            plan.paths.temporary_dir.mkdir(parents=True, exist_ok=True)
            emit_streams_selected(manifest, plan)

            subtitles: list[DownloadedSubtitle] = []
            if manifest.subtitles:
                subtitle_results = await asyncio.gather(
                    *(get_subtitle_lines(scope, url) for _, url in manifest.subtitles)
                )
                for (lang, _), lines in zip(manifest.subtitles, subtitle_results, strict=True):
                    if lines is not None:
                        subtitles.append(
                            DownloadedSubtitle(
                                lang=lang,
                                lines=tuple(
                                    DownloadedSubtitleLine(
                                        content=line.content,
                                        start=line.start,
                                        end=line.end,
                                    )
                                    for line in lines
                                ),
                            )
                        )

            danmaku_values: list[str | bytes] = []
            if manifest.danmaku_urls:
                if manifest.danmaku_source_type == "xml":
                    values = [
                        unwrap_fetch_result(await Fetcher.fetch_text(scope, url, encoding="utf-8"))
                        for url in manifest.danmaku_urls
                    ]
                else:
                    results = await asyncio.gather(*(Fetcher.fetch_bin(scope, url) for url in manifest.danmaku_urls))
                    values = [unwrap_fetch_result(result) for result in results]
                danmaku_values.extend(value for value in values if value is not None)
            danmaku = DownloadedDanmaku(
                source_type=manifest.danmaku_source_type,
                save_type=plan.resources.danmaku_save_type,
                data=tuple(danmaku_values),
            )

            cover_path = None
            if manifest.cover_url is not None:
                cover_data = unwrap_fetch_result(await Fetcher.fetch_bin(scope, manifest.cover_url))
                if cover_data is not None:
                    plan.paths.cover.write_bytes(cover_data)
                    cover_path = plan.paths.cover

            chapters: tuple[DownloadedChapter, ...] = ()
            if manifest.chapter_info_url is not None:
                chapter_info = await get_chapter_info(scope, manifest.chapter_info_url)
                if chapter_info is not None and chapter_info.points is not None:
                    chapters = tuple(
                        DownloadedChapter(
                            content=point.content,
                            start=point.start,
                            end=point.end,
                        )
                        for point in chapter_info.points
                    )
                elif chapter_info is not None:
                    emit_download_report("无法获取该视频的章节信息", ReportLevel.WARNING)

            downloaded = Downloaded(
                subtitles=tuple(subtitles),
                danmaku=danmaku,
                cover_path=cover_path,
                chapters=chapters,
            )

            artifacts: list[Artifact] = []
            emit_download_event(DownloadStageChanged(name=DownloadStage.WRITING_RESOURCES, item=plan.item))
            for resource in artifact_writer.write(metadata, plan, downloaded):
                artifacts.extend(resource.artifacts)
                if resource.kind is ArtifactKind.SUBTITLE:
                    emit_download_report(f"{', '.join(resource.labels)} 字幕已全部生成", badge="字幕")
                elif resource.kind is ArtifactKind.DANMAKU:
                    emit_download_report(f"{resource.labels[0]} 弹幕已生成".upper(), badge="弹幕")
                elif resource.kind is ArtifactKind.METADATA:
                    emit_download_report("NFO 媒体描述文件已生成", badge="描述文件")
                elif resource.kind is ArtifactKind.COVER:
                    emit_download_report("封面已生成", badge="封面")

            if not plan.has_media:
                emit_download_report("没有音视频需要下载", ReportLevel.WARNING)
                if not plan.media_requested:
                    return ItemResult(
                        state=ItemState.DONE,
                        artifacts=tuple(artifacts),
                    )
                emit_download_event(
                    DownloadItemSkipped(
                        item=plan.item,
                        reason=ItemSkipReason.NO_MEDIA_STREAM,
                    )
                )
                return ItemResult(
                    state=ItemState.SKIPPED,
                    skip_reason=ItemSkipReason.NO_MEDIA_STREAM,
                    artifacts=tuple(artifacts),
                )

            if plan.paths.output.exists():
                if not plan.overwrite:
                    emit_download_event(
                        DownloadItemSkipped(
                            item=plan.item,
                            reason=ItemSkipReason.ALREADY_EXISTS,
                        )
                    )
                    artifacts.append(Artifact(kind=ArtifactKind.MEDIA, path=plan.paths.output))
                    return ItemResult(
                        state=ItemState.SKIPPED,
                        output_path=plan.paths.output,
                        skip_reason=ItemSkipReason.ALREADY_EXISTS,
                        artifacts=tuple(artifacts),
                    )
                emit_download_report("文件已存在，因启用 overwrite 选项强制删除……")
                plan.paths.output.unlink()

            sources: list[tuple[str, tuple[str, ...]]] = []
            if plan.video is not None:
                video_resource = manifest.videos[plan.video.index]
                sources.append((video_resource.url, video_resource.mirrors))
            if plan.audio is not None:
                audio_resource = manifest.audios[plan.audio.index]
                sources.append((audio_resource.url, audio_resource.mirrors))

            emit_download_event(DownloadStageChanged(name=DownloadStage.DOWNLOADING, item=plan.item))
            emit_download_report("开始下载……")
            downloaded_paths = await download_files(
                scope,
                tuple(sources),
                block_size=plan.block_size,
                banned_mirrors_pattern=plan.banned_mirrors_pattern,
            )
            try:
                emit_download_report("下载完成！")
                downloaded_iter = iter(downloaded_paths)
                downloaded = replace(
                    downloaded,
                    video_path=next(downloaded_iter) if plan.video is not None else None,
                    audio_path=next(downloaded_iter) if plan.audio is not None else None,
                )

                emit_download_event(DownloadStageChanged(name=DownloadStage.POSTPROCESSING, item=plan.item))
                if plan.requires_audio_transcode_notice:
                    assert plan.audio is not None
                    emit_download_report(
                        f"输出容器 {plan.paths.output.suffix} 无法直接封装 {plan.audio.codec} 音频，"
                        f"将自动转码为 {plan.audio_save_codec}",
                    )
                await MediaMuxer().mux(
                    plan,
                    video_path=downloaded.video_path,
                    audio_path=downloaded.audio_path,
                    cover_path=downloaded.cover_path,
                    has_chapter_info=bool(downloaded.chapters),
                )
            finally:
                if downloaded_paths:
                    shutil.rmtree(downloaded_paths[0].parent, ignore_errors=True)

            artifacts.append(Artifact(kind=ArtifactKind.MEDIA, path=plan.paths.output))
            emit_download_event(DownloadArtifactCreated(item=plan.item, path=plan.paths.output))
            return ItemResult(
                state=ItemState.DONE,
                output_path=plan.paths.output,
                artifacts=tuple(artifacts),
            )
        finally:
            artifact_writer.cleanup_temporary(plan)


def emit_streams_selected(manifest: ResourceManifest, plan: DownloadPlan) -> None:
    emit_download_event(
        DownloadMediaSelected(
            item=plan.item,
            video=(
                SelectedVideoStream(
                    codec=plan.video.codec,
                    quality=plan.video.quality,
                    width=plan.video.width,
                    height=plan.video.height,
                    save_codec=plan.video_save_codec,
                )
                if plan.video is not None
                else None
            ),
            audio=(
                SelectedAudioStream(
                    codec=plan.audio.codec,
                    quality=plan.audio.quality,
                    save_codec=plan.audio_save_codec,
                )
                if plan.audio is not None
                else None
            ),
        )
    )
    selection = StreamSelection(
        video=manifest.videos[plan.video.index] if plan.video is not None else None,
        audio=manifest.audios[plan.audio.index] if plan.audio is not None else None,
        video_index=plan.video.index if plan.video is not None else None,
        audio_index=plan.audio.index if plan.audio is not None else None,
    )
    emit_manifest_formats(manifest, selection)
