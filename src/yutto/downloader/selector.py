from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto.exceptions import CryptoError
from yutto.stream import (
    gen_acodec_priority,
    gen_audio_quality_priority,
    gen_vcodec_priority,
    gen_video_quality_priority,
    is_encrypted_audio_quality,
    resolve_audio_codecs,
    resolve_audio_quality,
    resolve_video_codec_priority,
    resolve_video_codecs,
    resolve_video_quality,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.resource import ResourceManifest
    from yutto.scope import Scope
    from yutto.stream import AudioCodec, AudioQuality, VideoCodec, VideoQuality
    from yutto.types import AudioUrlMeta, VideoUrlMeta


@dataclass(frozen=True, slots=True)
class StreamSelection:
    """The exact media streams selected from one ResourceManifest."""

    video: VideoUrlMeta | None
    audio: AudioUrlMeta | None
    video_index: int | None
    audio_index: int | None


def select_video(
    videos: Sequence[VideoUrlMeta],
    video_quality: VideoQuality,
    video_codec: VideoCodec,
    video_download_codec_priority: Sequence[VideoCodec] | None = None,
) -> VideoUrlMeta | None:
    video_quality_priority = gen_video_quality_priority(video_quality)
    video_codec_priority = (
        gen_vcodec_priority(video_codec) if video_download_codec_priority is None else video_download_codec_priority
    )

    video_combined_priority = [
        (vqn, vcodec)
        for vqn in video_quality_priority
        # TODO: Dolby Selector
        for vcodec in video_codec_priority
    ]  # fmt: skip

    for vqn, vcodec in video_combined_priority:
        for video in videos:
            if video.quality == vqn and video.codec == vcodec:
                return video
    return None


def select_audio(
    audios: Sequence[AudioUrlMeta],
    audio_quality: AudioQuality,
    audio_codec: AudioCodec,
) -> AudioUrlMeta | None:
    if audios and all(is_encrypted_audio_quality(audio.quality) for audio in audios):
        raise CryptoError("yutto 目前不支持加密音频哦～")
    audio_quality_priority = gen_audio_quality_priority(audio_quality)
    audio_codec_priority = gen_acodec_priority(audio_codec)

    audio_combined_priority = [
        (aqn, acodec)
        for aqn in audio_quality_priority
        for acodec in audio_codec_priority
    ]  # fmt: skip

    for aqn, acodec in audio_combined_priority:
        for audio in audios:
            if audio.quality == aqn and audio.codec == acodec:
                return audio
    return None


def select_streams(resources: ResourceManifest, scope: Scope) -> StreamSelection:
    """Apply the active Scope's stream policy to one resolved manifest."""
    video_download_codec, _ = resolve_video_codecs(scope)
    audio_download_codec, _ = resolve_audio_codecs(scope)
    video = (
        select_video(
            resources.videos,
            resolve_video_quality(scope),
            video_download_codec,
            resolve_video_codec_priority(scope),
        )
        if resources.video_requested
        else None
    )
    audio = (
        select_audio(resources.audios, resolve_audio_quality(scope), audio_download_codec)
        if resources.audio_requested
        else None
    )
    return StreamSelection(
        video=video,
        audio=audio,
        video_index=resources.videos.index(video) if video is not None else None,
        audio_index=resources.audios.index(audio) if audio is not None else None,
    )
