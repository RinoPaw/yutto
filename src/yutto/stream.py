from __future__ import annotations

from typing import TYPE_CHECKING, cast

from yutto.config import DEFAULT_CONFIG
from yutto.media.codec import (
    AudioCodec,
    AudioCodecId,
    VideoCodec,
    VideoCodecId,
    audio_codec_map,
    audio_codec_priority_default,
    gen_acodec_priority,
    gen_vcodec_priority,
    video_codec_map,
    video_codec_priority_default,
)
from yutto.media.quality import (
    AudioCryptoQuality,
    AudioQuality,
    VideoQuality,
    audio_encrypted_quality_priorities,
    audio_quality_map,
    audio_quality_priority_default,
    gen_audio_quality_priority,
    gen_video_quality_priority,
    is_encrypted_audio_quality,
    video_quality_map,
    video_quality_priority_default,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from yutto.config import ResolvedConfig

DEFAULT_VIDEO_QUALITY = cast("VideoQuality", DEFAULT_CONFIG.stream.video_quality)
DEFAULT_AUDIO_QUALITY = cast("AudioQuality", DEFAULT_CONFIG.stream.audio_quality)

_default_video_codec = DEFAULT_CONFIG.stream.video_codec
assert isinstance(_default_video_codec, str)
_default_video_download_codec, DEFAULT_VIDEO_SAVE_CODEC = _default_video_codec.split(":", maxsplit=1)
DEFAULT_VIDEO_DOWNLOAD_CODEC = cast("VideoCodec", _default_video_download_codec)

_default_audio_codec = DEFAULT_CONFIG.stream.audio_codec
assert isinstance(_default_audio_codec, str)
_default_audio_download_codec, DEFAULT_AUDIO_SAVE_CODEC = _default_audio_codec.split(":", maxsplit=1)
DEFAULT_AUDIO_DOWNLOAD_CODEC = cast("AudioCodec", _default_audio_download_codec)


def resolve_video_quality(config: ResolvedConfig) -> VideoQuality:
    value = config.stream.video_quality
    if isinstance(value, bool) or not isinstance(value, int) or value not in video_quality_priority_default:
        raise ValueError(f"unsupported video quality: {value}")
    return value


def resolve_audio_quality(config: ResolvedConfig) -> AudioQuality:
    value = config.stream.audio_quality
    if isinstance(value, bool) or not isinstance(value, int) or value not in audio_quality_priority_default:
        raise ValueError(f"unsupported audio quality: {value}")
    return value


def resolve_video_codecs(config: ResolvedConfig) -> tuple[VideoCodec, str]:
    download_codec, save_codec = _split_codec_pair(config.stream.video_codec, "vcodec")
    if download_codec not in video_codec_priority_default:
        raise ValueError(f"unsupported video download codec: {download_codec}")
    return download_codec, save_codec


def resolve_audio_codecs(config: ResolvedConfig) -> tuple[AudioCodec, str]:
    download_codec, save_codec = _split_codec_pair(config.stream.audio_codec, "acodec")
    if download_codec not in audio_codec_priority_default:
        raise ValueError(f"unsupported audio download codec: {download_codec}")
    return download_codec, save_codec


def resolve_video_codec_priority(config: ResolvedConfig) -> Sequence[VideoCodec] | None:
    value = config.stream.video_codec_priority
    if value is None:
        return None
    if not isinstance(value, tuple) or not value:
        raise ValueError("video codec priority must be a non-empty sequence")
    if any(codec not in video_codec_priority_default for codec in value):
        raise ValueError("video codec priority contains an unsupported codec")
    download_codec, _ = resolve_video_codecs(config)
    if download_codec not in value:
        raise ValueError("video download codec must be included in video codec priority")
    return cast("Sequence[VideoCodec]", value)


def _split_codec_pair(value: object, option: str) -> tuple[str, str]:
    if value is None:
        raise ValueError(f"{option} must not be null")
    if not isinstance(value, str):
        raise TypeError(f"{option} must be a string")
    codecs = value.split(":")
    if len(codecs) != 2 or not all(codecs):
        raise ValueError(f"{option} must contain exactly one ':' separator and two codecs")
    return codecs[0], codecs[1]


__all__ = [
    "AudioCodec",
    "AudioCodecId",
    "AudioCryptoQuality",
    "AudioQuality",
    "DEFAULT_AUDIO_DOWNLOAD_CODEC",
    "DEFAULT_AUDIO_QUALITY",
    "DEFAULT_AUDIO_SAVE_CODEC",
    "DEFAULT_VIDEO_DOWNLOAD_CODEC",
    "DEFAULT_VIDEO_QUALITY",
    "DEFAULT_VIDEO_SAVE_CODEC",
    "VideoCodec",
    "VideoCodecId",
    "VideoQuality",
    "audio_codec_map",
    "audio_codec_priority_default",
    "audio_encrypted_quality_priorities",
    "audio_quality_map",
    "audio_quality_priority_default",
    "gen_acodec_priority",
    "gen_audio_quality_priority",
    "gen_vcodec_priority",
    "gen_video_quality_priority",
    "is_encrypted_audio_quality",
    "resolve_audio_codecs",
    "resolve_audio_quality",
    "resolve_video_codec_priority",
    "resolve_video_codecs",
    "resolve_video_quality",
    "video_codec_map",
    "video_codec_priority_default",
    "video_quality_map",
    "video_quality_priority_default",
]
