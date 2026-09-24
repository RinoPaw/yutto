from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest

from tests.test_processor.test_download_result import make_audio, make_resource_only_entry, make_scope
from yutto.core.events import DownloadMediaSelected, SelectedAudioStream, SelectedVideoStream
from yutto.core.operation import bind_download_event_sink
from yutto.downloader.executor import emit_streams_selected
from yutto.downloader.planner import DownloadPlan, DownloadPlanner
from yutto.scope import Scope
from yutto.stream import resolve_audio_codecs
from yutto.types import VideoUrlMeta

if TYPE_CHECKING:
    from yutto.resource import ResourceManifest
    from yutto.stream import AudioCodec, VideoCodec

pytestmark = pytest.mark.processor

OutputFormat = Literal["infer", "mp4", "mkv", "mov"]
AudioOnlyFormat = Literal["infer", "m4a", "aac", "mp3", "flac", "mp4", "mkv", "mov"]


def make_video(codec: VideoCodec = "avc") -> VideoUrlMeta:
    return VideoUrlMeta(
        url="https://signed.example.test/video?token=video-secret",
        mirrors=("https://mirror.example.test/video?token=mirror-secret",),
        codec=codec,
        width=1920,
        height=1080,
        quality=80,
    )


def make_plan(
    tmp_path: Path,
    *,
    video_codec: VideoCodec | None = None,
    audio_codec: AudioCodec | None = None,
    output_format: OutputFormat = "infer",
    audio_only_format: AudioOnlyFormat = "infer",
    path: Path = Path("series/episode"),
    use_output_as_temporary: bool = False,
) -> tuple[ResourceManifest, Scope, DownloadPlan]:
    manifest = replace(
        make_resource_only_entry(),
        videos=(make_video(video_codec),) if video_codec is not None else (),
        audios=(make_audio(audio_codec),) if audio_codec is not None else (),
    )
    base_scope = make_scope(
        tmp_path,
        video=video_codec is not None,
        audio=audio_codec is not None,
    )
    overrides: dict[str, object] = {
        "output.format": output_format,
        "output.audio_only_format": audio_only_format,
        "danmaku.block_keyword_patterns": ["original-pattern"],
    }
    if video_codec is not None:
        overrides["stream.video_codec"] = f"{video_codec}:copy"
    if audio_codec is not None:
        overrides["stream.audio_codec"] = f"{audio_codec}:copy"
    if use_output_as_temporary:
        overrides["output.temporary_directory"] = None
    scope = Scope(overrides, parent=base_scope)
    return manifest, scope, DownloadPlanner().plan(manifest, path, scope)


@pytest.mark.parametrize(
    ("video_codec", "audio_codec", "output_format", "audio_only_format", "suffix"),
    [
        ("avc", "flac", "infer", "infer", ".mkv"),
        (None, "flac", "infer", "infer", ".flac"),
        (None, "eac3", "infer", "infer", ".mkv"),
        (None, "mp4a", "infer", "mp3", ".mp3"),
        ("avc", "mp4a", "mov", "infer", ".mov"),
    ],
)
def test_planner_resolves_output_without_io(
    tmp_path: Path,
    video_codec: VideoCodec | None,
    audio_codec: AudioCodec | None,
    output_format: OutputFormat,
    audio_only_format: AudioOnlyFormat,
    suffix: str,
):
    _, _, plan = make_plan(
        tmp_path,
        video_codec=video_codec,
        audio_codec=audio_codec,
        output_format=output_format,
        audio_only_format=audio_only_format,
    )

    assert plan.paths.output == tmp_path / f"output/series/episode{suffix}"
    assert not (tmp_path / "output").exists()
    assert not (tmp_path / "temporary").exists()


def test_plan_selects_manifest_entries_without_copying_resource_urls(tmp_path: Path):
    manifest, scope, plan = make_plan(tmp_path, video_codec="avc", audio_codec="mp4a")
    patterns = scope.danmaku.block_keyword_patterns
    assert isinstance(patterns, list)
    patterns.append("later-pattern")

    assert plan.video is not None and plan.video.index == 0
    assert plan.audio is not None and plan.audio.index == 0
    assert not hasattr(plan.video, "url") and not hasattr(plan.video, "mirrors")
    assert not hasattr(plan.audio, "url") and not hasattr(plan.audio, "mirrors")
    assert plan.resources.danmaku.block_keyword_patterns == ("original-pattern",)
    assert "signed.example.test" not in repr(plan)
    assert "mirror.example.test" not in repr(plan)
    assert manifest.videos[0].url.startswith("https://signed.example.test/")


def test_stream_selection_event_projects_only_the_final_safe_media_values(tmp_path: Path):
    manifest, _, plan = make_plan(tmp_path, video_codec="av1", audio_codec="mp4a")
    events = []

    class Sink:
        def emit(self, event) -> None:
            events.append(event)

    with bind_download_event_sink(Sink()):
        emit_streams_selected(manifest, plan)

    assert events == [
        DownloadMediaSelected(
            item="episode",
            video=SelectedVideoStream(
                codec="av1",
                quality=80,
                width=1920,
                height=1080,
                save_codec="copy",
            ),
            audio=SelectedAudioStream(codec="mp4a", quality=30280, save_codec="copy"),
        )
    ]
    assert "signed.example.test" not in repr(events)
    assert "mirror.example.test" not in repr(events)


def test_planner_resolves_nested_temporary_paths_and_forced_transcode(tmp_path: Path):
    _, scope, plan = make_plan(
        tmp_path,
        audio_codec="mp4a",
        audio_only_format="mp3",
        path=Path("nested/series/episode"),
        use_output_as_temporary=True,
    )

    assert plan.paths.temporary_dir == tmp_path / "output/nested/series"
    assert not hasattr(plan.paths, "audio")
    assert not hasattr(plan.paths, "video")
    assert plan.paths.saved_cover == tmp_path / "output/nested/series/episode-poster.jpg"
    assert plan.audio_save_codec == "mp3"
    assert plan.requires_audio_transcode_notice is True
    assert resolve_audio_codecs(scope)[1] == "copy"
