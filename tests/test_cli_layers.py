from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from yutto.cli.compat import normalize_argv
from yutto.cli.input import expand_download_scopes, scope_values_from_cli
from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoConfig, scope_from_config
from yutto.scope import Scope

if TYPE_CHECKING:
    import argparse
    from pathlib import Path


pytestmark = pytest.mark.processor


def _parse_download(arguments: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(normalize_argv(arguments))


def _scope_from_args(arguments: list[str], config: YuttoConfig | None = None) -> Scope:
    config_scope = scope_from_config(config or YuttoConfig())
    values, _ = scope_values_from_cli(vars(_parse_download(arguments)))
    return Scope(values, parent=config_scope)


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

    scope = _scope_from_args(["BV1xx411c7mD", "--num-workers", "16", "--no-cover"], config)

    assert scope.network.download_workers == 16
    assert scope.resource.metadata is True
    assert scope.resource.cover is False


def test_empty_config_uses_root_scope_defaults():
    scope = _scope_from_args(["BV1xx411c7mD"])

    assert scope.network.download_workers == 8
    assert scope.stream.video_quality == 127
    assert scope.resource.video is True
    assert scope.resource.metadata is False


def test_explicit_auto_priority_clears_configured_codec_priority():
    config = YuttoConfig.model_validate(
        {
            "basic": {
                "vcodec": "avc:copy",
                "download_vcodec_priority": ["avc", "hevc"],
            }
        }
    )

    scope = _scope_from_args(["BV1xx411c7mD", "--download-vcodec-priority", "auto"], config)

    assert scope.stream.video_codec_priority is None


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
    config = scope_from_config(YuttoConfig())
    outer_raw = vars(
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
    outer_values, no_inherit = scope_values_from_cli(outer_raw)

    scopes = expand_download_scopes(
        Scope(outer_values, parent=config),
        parser,
        config,
        no_inherit=no_inherit,
    )

    assert [(scope.source.value, scope.network.proxy, scope.network.fetch_workers) for scope in scopes] == [
        ("BV1first", "no", 2),
        ("BV1second", "auto", 5),
    ]
