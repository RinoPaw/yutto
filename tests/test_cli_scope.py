from __future__ import annotations

from typing import TYPE_CHECKING

from yutto.cli.auth import resolve_auth_command_options
from yutto.cli.compat import normalize_argv
from yutto.cli.credentials import resolve_credential_options
from yutto.cli.input import config_values_from_cli, expand_download_configs
from yutto.cli.parser import build_parser
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.settings import YuttoConfig, resolved_config_from_settings
from yutto.scope import MISSING, ResolvedConfig, merge_configs

if TYPE_CHECKING:
    from pathlib import Path


def test_config_merge_preserves_explicit_none_without_parent_chain():
    configured = ResolvedConfig({"network.proxy": "config", "output.temporary_directory": "config"})
    cli = merge_configs(
        configured,
        ResolvedConfig({"network.proxy": "cli", "output.temporary_directory": None}),
    )

    assert cli.network.proxy == "cli"
    assert cli.output.temporary_directory is None
    assert cli.stream.video_quality is MISSING


def test_persistent_settings_map_to_resolved_config_specs():
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

    resolved = resolved_config_from_settings(config)

    assert resolved.network.download_workers == 12
    assert resolved.output.metadata_premiered_format == "%Y-%m-%d"
    assert resolved.runtime.ffmpeg_path == "/opt/ffmpeg"
    assert resolved.danmaku.font_size == 36
    assert isinstance(resolved.selection.published_since, int)
    assert resolved.auth.profile == "work"


def test_no_inherit_uses_persistent_baseline_instead_of_outer_config(tmp_path: Path):
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
    configured = resolved_config_from_settings(config)
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
    values, no_inherit = config_values_from_cli(raw)
    outer = merge_configs(configured, ResolvedConfig(values))

    first, second = expand_download_configs(outer, parser, configured, no_inherit=no_inherit)

    assert first.network.proxy == "no"
    assert first.network.fetch_workers == 2
    assert second.network.proxy == "config-proxy"
    assert second.network.fetch_workers == 5


def test_resolved_config_feeds_runtime_and_credentials():
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
    configured = resolved_config_from_settings(config)
    cli = merge_configs(
        configured,
        ResolvedConfig(
            {
                "source.value": "BV1xx411c7mD",
                "runtime.jobs": 5,
                "network.proxy": "no",
                "stream.video_codec_priority": None,
                "auth.profile": "cli-profile",
            }
        ),
    )

    runtime = resolve_runtime_options(cli)
    credentials = resolve_credential_options([cli])[0]

    assert cli.network.proxy == "no"
    assert cli.stream.video_codec_priority is None
    assert runtime.jobs == 5
    assert runtime.ffmpeg_path == "/config/ffmpeg"
    assert credentials.auth_profile == "cli-profile"


def test_auth_command_uses_same_resolved_config():
    config = YuttoConfig.model_validate(
        {
            "basic": {"proxy": "config-proxy"},
            "auth": {
                "auth": "SESSDATA=config",
                "auth_profile": "config-profile",
            },
        }
    )
    configured = resolved_config_from_settings(config)
    cli = merge_configs(
        configured,
        ResolvedConfig(
            {
                "auth.profile": "cli-profile",
                "auth.mode": "web",
            }
        ),
    )

    options = resolve_auth_command_options(cli, "login")

    assert options.auth_command == "login"
    assert options.auth == "SESSDATA=config"
    assert options.auth_profile == "cli-profile"
    assert options.proxy == "config-proxy"
    assert options.mode == "web"
    assert options.poll_interval == 2.0
    assert options.timeout == 180


def test_empty_settings_resolve_application_defaults():
    resolved = resolved_config_from_settings(YuttoConfig())
    config = merge_configs(resolved, ResolvedConfig({"source.value": "BV1xx411c7mD"}))

    runtime = resolve_runtime_options(config)

    assert config.network.download_workers == 8
    assert config.stream.video_quality == 127
    assert runtime.jobs == 1
    assert runtime.ffmpeg_path is None
