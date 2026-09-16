from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from yutto.cli.bootstrap import parse_bootstrap_args
from yutto.cli.command import download_layer_from_namespace, resolve_download_command
from yutto.cli.compat import normalize_argv
from yutto.cli.input import expand_download_layers
from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoSettings

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


def test_cli_overrides_config_while_unmentioned_config_values_survive():
    settings = YuttoSettings.model_validate(
        {
            "basic": {"num_workers": 12},
            "resource": {"require_metadata": True, "require_cover": True},
        }
    )
    args = _parse_download(["BV1xx411c7mD", "--num-workers", "16", "--no-cover"])

    command = resolve_download_command(download_layer_from_namespace(args), settings)

    assert command.request.network.download_workers == 16
    assert command.request.resources.metadata is True
    assert command.request.resources.cover is False


def test_empty_config_uses_core_request_defaults():
    args = _parse_download(["BV1xx411c7mD"])

    command = resolve_download_command(download_layer_from_namespace(args), YuttoSettings())

    assert command.request.network.download_workers == 8
    assert command.request.stream.video_quality == 127
    assert command.request.resources.video is True
    assert command.request.resources.metadata is False


def test_explicit_auto_priority_clears_configured_codec_priority():
    settings = YuttoSettings.model_validate(
        {
            "basic": {
                "vcodec": "avc:copy",
                "download_vcodec_priority": ["avc", "hevc"],
            }
        }
    )
    args = _parse_download(["BV1xx411c7mD", "--download-vcodec-priority", "auto"])

    command = resolve_download_command(download_layer_from_namespace(args), settings)

    assert command.request.stream.video_download_codec_priority is None


def test_task_list_inheritance_merges_explicit_layers(tmp_path: Path):
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
    outer = download_layer_from_namespace(
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

    layers = expand_download_layers(outer, parser, YuttoSettings())
    requests = [resolve_download_command(layer, YuttoSettings()).request for layer in layers]

    assert [(request.source.url, request.network.proxy, request.network.fetch_workers) for request in requests] == [
        ("BV1first", "no", 2),
        ("BV1second", "auto", 5),
    ]


def test_bootstrap_config_is_found_independently_of_argument_order(tmp_path: Path):
    config = tmp_path / "yutto.toml"

    options = parse_bootstrap_args(["BV1xx411c7mD", "--video-quality", "80", "--config", str(config)])

    assert options.config == config
