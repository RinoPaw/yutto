from __future__ import annotations

import asyncio
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

import yutto.downloader.executor as executor_module
from yutto.core.execution import ExecutionScope
from yutto.core.request import DownloadRequest
from yutto.core.result import Artifact, ArtifactKind, ItemResult, ItemSkipReason, ItemState
from yutto.downloader.downloader import process_download
from yutto.downloader.media_muxer import MediaMuxer
from yutto.downloader.resource_fetcher import FetchedResources
from yutto.exceptions import PostprocessingError
from yutto.resource import ResourceManifest
from yutto.utils.danmaku import write_danmaku
from yutto.utils.functional import as_sync
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    from yutto.downloader.planner import DownloadPlan
    from yutto.stream import AudioCodec
    from yutto.types import AudioUrlMeta
    from yutto.utils.danmaku import DanmakuData, DanmakuOptions

pytestmark = pytest.mark.processor


ENTRY_PATH = Path("series/episode")


def make_request(
    tmp_path: Path,
    *,
    video: bool = False,
    audio: bool = False,
    save_cover: bool = True,
    metadata: bool = True,
    chapter_info: bool = False,
) -> DownloadRequest:
    return DownloadRequest.model_validate(
        {
            "source": {"url": "BV1test"},
            "resources": {
                "video": video,
                "audio": audio,
                "metadata": metadata,
                "chapter_info": chapter_info,
                "save_cover": save_cover,
            },
            "stream": {
                "video_quality": 80,
                "video_download_codec": "avc",
                "video_save_codec": "copy",
                "audio_quality": 30280,
                "audio_download_codec": "mp4a",
                "audio_save_codec": "copy",
            },
            "output": {
                "directory": tmp_path / "output",
                "temporary_directory": tmp_path / "temporary",
            },
        }
    )


def make_metadata() -> ItemMetaData:
    return ItemMetaData(
        title="测试",
        show_title="测试",
        original_filename="episode",
    )


def make_resource_only_entry() -> ResourceManifest:
    return ResourceManifest(
        subtitles=(("zh-CN", "https://example.test/subtitle.json"),),
        danmaku_source_type="xml",
        danmaku_save_type="xml",
        danmaku_urls=("https://example.test/danmaku.xml",),
        cover_url="https://example.test/cover.jpg",
    )


def make_audio(codec: AudioCodec = "mp4a") -> AudioUrlMeta:
    return {
        "url": "https://signed.example.test/audio?token=audio-secret",
        "mirrors": ["https://mirror.example.test/audio?token=mirror-secret"],
        "codec": codec,
        "width": 0,
        "height": 0,
        "quality": 30280,
    }


def make_media_entry() -> ResourceManifest:
    return replace(
        make_resource_only_entry(),
        audios=(make_audio(),),
        chapter_info_url="https://example.test/chapters.json",
    )


@pytest.fixture(autouse=True)
def stub_fetched_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fetch_resources(_scope: ExecutionScope, manifest: ResourceManifest) -> FetchedResources:
        subtitles = (
            (
                {
                    "lang": "zh-CN",
                    "lines": [{"content": "测试", "from": 0, "to": 1}],
                },
            )
            if manifest.subtitles
            else ()
        )
        danmaku = (
            {"source_type": "xml", "save_type": manifest.danmaku_save_type, "data": ["<i />"]}
            if manifest.danmaku_urls
            else {"source_type": None, "save_type": None, "data": []}
        )
        chapters = (
            ({"start": 0, "end": 1, "content": "chapter"},)
            if manifest.chapter_info_url is not None
            else ()
        )
        return FetchedResources(
            danmaku=cast("DanmakuData", danmaku),
            subtitles=cast("Any", subtitles),
            cover_data=b"cover" if manifest.cover_url is not None else None,
            chapter_info_data=chapters,
        )

    monkeypatch.setattr(executor_module, "fetch_resources", fetch_resources)


@pytest.mark.parametrize("cancelled", [False, True], ids=["failure", "cancellation"])
@as_sync
async def test_interrupted_mux_keeps_resume_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cancelled: bool,
):
    started = asyncio.Event()

    class InterruptedFFmpeg:
        async def exec_async(self, args: list[str]) -> subprocess.CompletedProcess[bytes]:
            Path(args[-1]).write_bytes(b"partial output")
            if cancelled:
                started.set()
                await asyncio.Event().wait()
            return subprocess.CompletedProcess(args, 1, b"", b"ffmpeg failed")

    async def write_audio_fragment(_scope: ExecutionScope, plan: DownloadPlan) -> None:
        plan.paths.audio.write_bytes(b"resumable audio")

    muxer = MediaMuxer(InterruptedFFmpeg())
    monkeypatch.setattr(executor_module, "download_video_and_audio", write_audio_fragment)
    monkeypatch.setattr(executor_module, "MediaMuxer", lambda: muxer)
    execution = asyncio.create_task(
        process_download(
            ExecutionScope(cast("Any", object())),
            make_media_entry(),
            make_metadata(),
            ENTRY_PATH,
            make_request(tmp_path, audio=True, chapter_info=True),
        )
    )
    if cancelled:
        await started.wait()
        execution.cancel()
        error = asyncio.CancelledError
    else:
        error = PostprocessingError

    with pytest.raises(error):
        await execution

    output_dir = tmp_path / "output/series"
    temporary_dir = tmp_path / "temporary/series"
    assert (output_dir / "episode.zh-CN.srt").exists()
    assert (temporary_dir / "episode_audio.m4s").read_bytes() == b"resumable audio"
    assert (temporary_dir / "episode_cover.jpg").exists()
    assert (temporary_dir / "episode_chapter_info.ini").exists()
    assert not (output_dir / "episode.m4a").exists()


@as_sync
async def test_resource_only_download_returns_final_artifacts_without_temporary_files(tmp_path: Path):
    result = await process_download(
        ExecutionScope(cast("Any", object())),
        make_resource_only_entry(),
        make_metadata(),
        ENTRY_PATH,
        make_request(tmp_path),
    )

    output_dir = tmp_path / "output/series"
    assert result == ItemResult(
        state=ItemState.DONE,
        output_path=output_dir / "episode.m4a",
        artifacts=(
            Artifact(kind=ArtifactKind.SUBTITLE, path=output_dir / "episode.zh-CN.srt"),
            Artifact(kind=ArtifactKind.DANMAKU, path=output_dir / "episode.xml"),
            Artifact(kind=ArtifactKind.METADATA, path=output_dir / "episode.nfo"),
            Artifact(kind=ArtifactKind.COVER, path=output_dir / "episode-poster.jpg"),
        ),
    )
    assert all(artifact.path.exists() for artifact in result.artifacts)
    assert not (tmp_path / "temporary/series/episode_cover.jpg").exists()


@as_sync
async def test_existing_media_returns_artifacts_and_cleans_temporary_resources(tmp_path: Path):
    entry = replace(
        make_media_entry(),
        danmaku_source_type=None,
        danmaku_save_type=None,
        danmaku_urls=(),
    )
    output_path = tmp_path / "output/series/episode.m4a"
    subtitle_path = tmp_path / "output/series/episode.zh-CN.srt"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"existing")
    subtitle_path.write_text("stale subtitle")

    result = await process_download(
        ExecutionScope(cast("Any", object())),
        entry,
        make_metadata(),
        ENTRY_PATH,
        make_request(tmp_path, audio=True, metadata=False, chapter_info=True),
    )

    assert result == ItemResult(
        state=ItemState.SKIPPED,
        output_path=output_path,
        skip_reason=ItemSkipReason.ALREADY_EXISTS,
        artifacts=(
            Artifact(kind=ArtifactKind.SUBTITLE, path=subtitle_path),
            Artifact(kind=ArtifactKind.COVER, path=tmp_path / "output/series/episode-poster.jpg"),
            Artifact(kind=ArtifactKind.MEDIA, path=output_path),
        ),
    )
    assert subtitle_path.read_text() != "stale subtitle"
    assert not (tmp_path / "temporary/series/episode_cover.jpg").exists()
    assert not (tmp_path / "temporary/series/episode_chapter_info.ini").exists()


@as_sync
async def test_missing_requested_audio_does_not_clean_uncreated_video_file(tmp_path: Path):
    entry = ResourceManifest(
        videos=(
            {
                "url": "https://example.test/video",
                "mirrors": [],
                "codec": "avc",
                "width": 1920,
                "height": 1080,
                "quality": 80,
            },
        ),
    )

    result = await process_download(
        ExecutionScope(cast("Any", object())),
        entry,
        make_metadata(),
        ENTRY_PATH,
        make_request(tmp_path, audio=True, save_cover=False, metadata=False),
    )

    assert result == ItemResult(
        state=ItemState.SKIPPED,
        output_path=tmp_path / "output/series/episode.m4a",
        skip_reason=ItemSkipReason.NO_MEDIA_STREAM,
    )


def test_multi_part_protobuf_danmaku_returns_every_output_path(tmp_path: Path):
    danmaku = cast(
        "DanmakuData",
        {"source_type": "protobuf", "save_type": "protobuf", "data": [b"first", b"second"]},
    )

    paths = write_danmaku(danmaku, tmp_path / "video.mp4", 1080, 1920, cast("DanmakuOptions", {}))

    assert paths == [tmp_path / "video_00.pb", tmp_path / "video_01.pb"]
    assert [path.read_bytes() for path in paths] == [b"first", b"second"]
