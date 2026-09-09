from __future__ import annotations

import asyncio
import shutil
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from yutto.core.events import (
    DownloadArtifactCreated,
    DownloadItemSkipped,
    DownloadMediaSelected,
    DownloadStage,
    DownloadStageChanged,
    SelectedAudioStream,
    SelectedVideoStream,
)
from yutto.core.operation import ReportColor, ReportLevel, emit_download_event, emit_download_report
from yutto.core.result import Artifact, ArtifactKind, ItemResult, ItemSkipReason, ItemState
from yutto.downloader.artifact_writer import ArtifactWriter
from yutto.downloader.media_muxer import MediaMuxer
from yutto.downloader.transfer import download_files
from yutto.media.quality import audio_quality_map, video_quality_map
from yutto.types import MultiLangSubtitle
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.functional import data_has_chained_keys
from yutto.utils.metadata import ChapterInfoData

if TYPE_CHECKING:
    from pathlib import Path

    from yutto.core.execution import ExecutionScope
    from yutto.downloader.planner import DownloadPlan
    from yutto.resource import ResourceManifest
    from yutto.utils.danmaku import DanmakuData
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

            subtitles: list[MultiLangSubtitle] = []
            if manifest.subtitles:
                subtitle_results = await asyncio.gather(
                    *(Fetcher.fetch_json(scope, url) for _, url in manifest.subtitles)
                )
                for (lang, _), result in zip(manifest.subtitles, subtitle_results, strict=True):
                    subtitle_json = result.value_or(None)
                    if subtitle_json is not None and "body" in subtitle_json:
                        subtitles.append(MultiLangSubtitle(lang=lang, lines=subtitle_json["body"]))

            danmaku = cast(
                "DanmakuData",
                {
                    "source_type": manifest.danmaku_source_type,
                    "save_type": manifest.danmaku_save_type,
                    "data": [],
                },
            )
            if manifest.danmaku_urls:
                if manifest.danmaku_source_type == "xml":
                    values = [
                        unwrap_fetch_result(await Fetcher.fetch_text(scope, url, encoding="utf-8"))
                        for url in manifest.danmaku_urls
                    ]
                else:
                    results = await asyncio.gather(*(Fetcher.fetch_bin(scope, url) for url in manifest.danmaku_urls))
                    values = [unwrap_fetch_result(result) for result in results]
                danmaku["data"].extend(value for value in values if value is not None)

            cover_data = (
                unwrap_fetch_result(await Fetcher.fetch_bin(scope, manifest.cover_url))
                if manifest.cover_url is not None
                else None
            )

            chapter_info_data: tuple[ChapterInfoData, ...] = ()
            if manifest.chapter_info_url is not None:
                chapter_json = (await Fetcher.fetch_json(scope, manifest.chapter_info_url)).value_or(None)
                if chapter_json is not None and data_has_chained_keys(chapter_json, ["data", "view_points"]):
                    chapter_info_data = tuple(
                        ChapterInfoData(content=item["content"], start=item["from"], end=item["to"])
                        for item in chapter_json["data"]["view_points"]
                    )
                elif chapter_json is not None:
                    emit_download_report("无法获取该视频的章节信息", ReportLevel.WARNING)

            metadata_for_write = (
                replace(metadata, chapter_info_data=list(chapter_info_data))
                if chapter_info_data
                else metadata
            )

            artifacts: list[Artifact] = []
            emit_download_event(DownloadStageChanged(name=DownloadStage.WRITING_RESOURCES, item=plan.item))
            for resource in artifact_writer.write(
                metadata_for_write,
                plan,
                subtitles=tuple(subtitles),
                danmaku=danmaku,
                cover_data=cover_data,
                chapter_info_data=chapter_info_data,
            ):
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
                        output_path=plan.paths.output,
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
                    output_path=plan.paths.output,
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
                sources.append((video_resource["url"], tuple(video_resource["mirrors"])))
            if plan.audio is not None:
                audio_resource = manifest.audios[plan.audio.index]
                sources.append((audio_resource["url"], tuple(audio_resource["mirrors"])))

            emit_download_event(DownloadStageChanged(name=DownloadStage.DOWNLOADING, item=plan.item))
            emit_download_report("开始下载……")
            downloaded = await download_files(
                scope,
                tuple(sources),
                block_size=plan.block_size,
                banned_mirrors_pattern=plan.banned_mirrors_pattern,
            )
            try:
                emit_download_report("下载完成！")
                downloaded_iter = iter(downloaded)
                video_path: Path | None = next(downloaded_iter) if plan.video is not None else None
                audio_path: Path | None = next(downloaded_iter) if plan.audio is not None else None

                emit_download_event(DownloadStageChanged(name=DownloadStage.POSTPROCESSING, item=plan.item))
                if plan.requires_audio_transcode_notice:
                    assert plan.audio is not None
                    emit_download_report(
                        f"输出容器 {plan.paths.output.suffix} 无法直接封装 {plan.audio.codec} 音频，"
                        f"将自动转码为 {plan.audio_save_codec}",
                    )
                await MediaMuxer().mux(
                    plan,
                    video_path=video_path,
                    audio_path=audio_path,
                    has_cover=cover_data is not None,
                    has_chapter_info=bool(chapter_info_data),
                )
            finally:
                if downloaded:
                    shutil.rmtree(downloaded[0].parent, ignore_errors=True)

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
    videos = manifest.videos
    selected_video_index = plan.video.index if plan.video is not None else -1
    if not videos:
        emit_download_report("不包含任何视频流")
    else:
        emit_download_report(f"共包含以下 {len(videos)} 个视频流：")
        for index, candidate in enumerate(videos):
            selected = index == selected_video_index
            message = "{}{:2} [{:^4}] [{:>4}x{:<4}] <{:^8}> #{}".format(
                "*" if selected else " ",
                index,
                candidate["codec"].upper(),
                candidate["width"],
                candidate["height"],
                video_quality_map[candidate["quality"]]["description"],
                len(candidate["mirrors"]) + 1,
            )
            emit_download_report(message, color=ReportColor.BLUE if selected else None)

    audios = manifest.audios
    selected_audio_index = plan.audio.index if plan.audio is not None else -1
    if not audios:
        emit_download_report("不包含任何音频流")
    else:
        emit_download_report(f"共包含以下 {len(audios)} 个音频流：")
        for index, candidate in enumerate(audios):
            selected = index == selected_audio_index
            message = "{}{:2} [{:^4}] <{:^8}>".format(
                "*" if selected else " ",
                index,
                candidate["codec"].upper(),
                audio_quality_map[candidate["quality"]]["description"],
            )
            emit_download_report(
                message,
                color=ReportColor.MAGENTA if selected else None,
            )
