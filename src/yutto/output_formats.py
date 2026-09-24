from __future__ import annotations

from typing import Literal

OutputFormat = Literal["infer", "mp4", "mkv", "mov"]
AudioOnlyOutputFormat = Literal["infer", "m4a", "aac", "mp3", "flac", "mp4", "mkv", "mov"]

OUTPUT_FORMATS: tuple[OutputFormat, ...] = ("infer", "mp4", "mkv", "mov")
AUDIO_ONLY_OUTPUT_FORMATS: tuple[AudioOnlyOutputFormat, ...] = (
    "infer",
    "m4a",
    "aac",
    "mp3",
    "flac",
    "mp4",
    "mkv",
    "mov",
)


def resolve_output_format(value: object) -> OutputFormat:
    if not isinstance(value, str) or value not in OUTPUT_FORMATS:
        raise ValueError(f"unsupported output format: {value}")
    return value


def resolve_audio_only_output_format(value: object) -> AudioOnlyOutputFormat:
    if not isinstance(value, str) or value not in AUDIO_ONLY_OUTPUT_FORMATS:
        raise ValueError(f"unsupported audio-only output format: {value}")
    return value


__all__ = [
    "AUDIO_ONLY_OUTPUT_FORMATS",
    "OUTPUT_FORMATS",
    "AudioOnlyOutputFormat",
    "OutputFormat",
    "resolve_audio_only_output_format",
    "resolve_output_format",
]
