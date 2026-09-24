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


def _download_option_choices(option: str) -> tuple[str, ...]:
    parser = build_parser()
    download = next(action for action in parser._actions if action.dest == "command").choices["download"]
    action = next(action for action in download._actions if option in action.option_strings)
    assert action.choices is not None
    return tuple(action.choices)


def test_output_format_contract_is_shared_by_cli_and_config() -> None:
    assert _download_option_choices("--output-format") == OUTPUT_FORMATS
    assert _download_option_choices("--output-format-audio-only") == AUDIO_ONLY_OUTPUT_FORMATS
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
