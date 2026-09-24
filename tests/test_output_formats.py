from __future__ import annotations

import pytest

from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoBasicConfig
from yutto.output_formats import (
    AUDIO_ONLY_OUTPUT_FORMATS,
    OUTPUT_FORMATS,
    resolve_audio_only_output_format,
    resolve_output_format,
)

pytestmark = pytest.mark.processor


def _parse_download(*args: str):
    return build_parser().parse_args(["download", "BV1test", *args])


@pytest.mark.parametrize("output_format", OUTPUT_FORMATS)
def test_cli_accepts_every_output_format_from_shared_contract(output_format: str) -> None:
    assert _parse_download("--output-format", output_format).output_format == output_format


@pytest.mark.parametrize("output_format", AUDIO_ONLY_OUTPUT_FORMATS)
def test_cli_accepts_every_audio_only_output_format_from_shared_contract(output_format: str) -> None:
    assert _parse_download("--output-format-audio-only", output_format).output_format_audio_only == output_format


def test_output_format_contract_is_shared_by_config_and_resolvers() -> None:
    assert YuttoBasicConfig(output_format="mkv").output_format == resolve_output_format("mkv")
    assert YuttoBasicConfig(output_format_audio_only="flac").output_format_audio_only == resolve_audio_only_output_format(
        "flac"
    )


@pytest.mark.parametrize("value", [None, "webm", 1])
def test_output_format_resolvers_reject_values_outside_contract(value: object) -> None:
    with pytest.raises(ValueError, match="unsupported output format"):
        resolve_output_format(value)
    with pytest.raises(ValueError, match="unsupported audio-only output format"):
        resolve_audio_only_output_format(value)


def test_cli_rejects_output_formats_outside_contract() -> None:
    with pytest.raises(SystemExit):
        _parse_download("--output-format", "webm")
    with pytest.raises(SystemExit):
        _parse_download("--output-format-audio-only", "webm")
