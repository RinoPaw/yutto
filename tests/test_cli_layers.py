from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from yutto.cli.compat import normalize_argv
from yutto.cli.input import expand_download_values
from yutto.cli.parser import build_parser
from yutto.cli.request_adapter import resolve_download_request
from yutto.cli.settings import YuttoConfig

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


pytestmark = pytest.mark.processor


def _parse_download(arguments: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(normalize_argv(arguments))


def test_download_parser_emits_only_explicit_cli_values():
    args = _parse_download(["BV1xx411c7mD"])

    assert vars(args) == {
        "command": "download",
        "source": "BV1xx411c7mD",
    }


def test_yutto_config_is_immutable():
    config = YuttoConfig.model_validate({"basic": {"jobs": 2}})

    with pytest.raises(ValidationError, match="frozen"):
        config.basic.__setattr__("jobs", 4)


def test_cli_overrides_config_while_unmentioned_config_values_survive():
    config = YuttoConfig.model_validate(
        {
            "basic": {"num_workers": 12},
            "resource": {"require_metadata": True, "require_cover": True},
        }
    )
    args = _parse_download(["BV1xx411c7mD", "--num-workers", "16", "--no-cover"])

    request = resolve_download_request(vars(args), config)

    assert request.network.download_workers == 16
    assert request.resources.metadata is True
    assert request.resources.cover is False


def test_empty_config_uses_core_request_defaults():
    args = _parse_download(["BV1xx411c7mD"])

    request = resolve_download_request(vars(args), YuttoConfig())

    assert request.network.download_workers == 8
    assert request.stream.video_quality == 127
    assert request.resources.video is True
    assert request.resources.metadata is False


def test_explicit_auto_priority_clears_configured_codec_priority():
    config = YuttoConfig.model_validate(
        {
            "basic": {
                "vcodec": "avc:copy",
                "download_vcodec_priority": ["avc", "hevc"],
            }
        }
    )
    args = _parse_download(["BV1xx411c7mD", "--download-vcodec-priority", "auto"])

    request = resolve_download_request(vars(args), config)

    assert request.stream.video_download_codec_priority is None


def test_task_list_inheritance_merges_explicit_values(tmp_path: Path):
    task_list = tmp_path / "downloads.txt"
    task_list.write_text(
        "\n".join(
            [
                "BV1first --fetch-workers 2",
                "BV1second --no-inherit --fetch-workers 5",
            ]
        ),
        encoding="utf-8",
    )
    parser = build_parser()
    outer = vars(
        parser.parse_args(
            normalize_argv(
                [
                    str(task_list),
                    "--proxy",
                    "no",
                    "--fetch-workers",
                    "11",
                ]
            )
        )
    )

    tasks = expand_download_values(outer, parser, YuttoConfig())
    requests = [resolve_download_request(task, YuttoConfig()) for task in tasks]

    assert [(request.source.url, request.network.proxy, request.network.fetch_workers) for request in requests] == [
        ("BV1first", "no", 2),
        ("BV1second", "auto", 5),
    ]
