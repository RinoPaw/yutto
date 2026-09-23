from __future__ import annotations

from typing import TYPE_CHECKING

from yutto.cli.auth import resolve_auth_command_options
from yutto.cli.compat import normalize_argv
from yutto.cli.credentials import resolve_credential_options
from yutto.cli.input import expand_download_scopes, scope_values_from_cli
from yutto.cli.parser import build_parser
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.settings import YuttoConfig, scope_from_config
from yutto.scope import MISSING, Scope

if TYPE_CHECKING:
    from pathlib import Path


def test_scope_uses_lexical_shadowing_and_preserves_explicit_none():
    configured = Scope({"network.proxy": "config", "output.temporary_directory": "config"})
    cli = Scope({"network.proxy": "cli", "output.temporary_directory": None}, parent=configured)

    assert cli.network.proxy == "cli"
    assert cli.output.temporary_directory is None
    assert cli.stream.video_quality is MISSING


def test_config_scope_maps_persistent_names_to_scope_specs():
    config = YuttoConfig.model_validate(
        {
            "basic": {
                "download_workers": 12,
                "metadata_premiered_format": "%Y-%m-%d",
                "ffmpeg_path": "/opt/ffmpeg",
            },
            "danmaku": {"danmaku_font_size": 36},
            "batch": {"published_since": "2026-01-01"},
            "auth": {"auth_profile": "work"},
        }
    )

    scope = scope_from_config(config)

    assert scope.network.download_workers == 12
    assert scope.output.metadata_premiered_format == "%Y-%m-%d"
    assert scope.runtime.ffmpeg_path == "/opt/ffmpeg"
    assert scope.danmaku.font_size == 36
    assert scope.selection.published_since == "2026-01-01"
    assert scope.auth.profile == "work"


def test_no_inherit_cuts_parent_cli_scope_but_keeps_config_scope(tmp_path: Path):
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
    config = YuttoConfig.model_validate({"basic": {"proxy": "config-proxy"}})
    configured = scope_from_config(config)
    raw = vars(
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
    values, no_inherit = scope_values_from_cli(raw)
    outer = Scope(values, parent=configured)

    first, second = expand_download_scopes(outer, parser, configured, no_inherit=no_inherit)

    assert first.network.proxy == "no"
    assert first.network.fetch_workers == 2
    assert second.network.proxy == "config-proxy"
    assert second.network.fetch_workers == 5


def test_scope_feeds_runtime_and_credentials_from_one_chain():
    config = YuttoConfig.model_validate(
        {
            "basic": {
                "jobs": 3,
                "proxy": "config-proxy",
                "ffmpeg_path": "/config/ffmpeg",
            },
            "auth": {"auth_profile": "config-profile"},
        }
    )
    configured = scope_from_config(config)
    cli = Scope(
        {
            "source.value": "BV1xx411c7mD",
            "runtime.jobs": 5,
            "network.proxy": "no",
            "stream.video_codec_priority": None,
            "auth.profile": "cli-profile",
        },
        parent=configured,
    )

    runtime = resolve_runtime_options(cli)
    credentials = resolve_credential_options([cli])[0]

    assert cli.network.proxy == "no"
    assert cli.stream.video_codec_priority is None
    assert runtime.jobs == 5
    assert runtime.ffmpeg_path == "/config/ffmpeg"
    assert credentials.auth_profile == "cli-profile"


def test_auth_command_uses_the_same_scope_chain():
    config = YuttoConfig.model_validate(
        {
            "basic": {"proxy": "config-proxy"},
            "auth": {
                "auth": "SESSDATA=config",
                "auth_profile": "config-profile",
            },
        }
    )
    configured = scope_from_config(config)
    cli = Scope(
        {
            "auth.profile": "cli-profile",
            "auth.mode": "web",
        },
        parent=configured,
    )

    options = resolve_auth_command_options(cli, "login")

    assert options.auth_command == "login"
    assert options.auth == "SESSDATA=config"
    assert options.auth_profile == "cli-profile"
    assert options.proxy == "config-proxy"
    assert options.mode == "web"
    assert options.poll_interval == 2.0
    assert options.timeout == 180


def test_empty_scope_inherits_root_defaults():
    configured = scope_from_config(YuttoConfig())
    cli = Scope({"source.value": "BV1xx411c7mD"}, parent=configured)

    runtime = resolve_runtime_options(cli)

    assert cli.network.download_workers == 8
    assert cli.stream.video_quality == 127
    assert runtime.jobs == 1
    assert runtime.ffmpeg_path is None
