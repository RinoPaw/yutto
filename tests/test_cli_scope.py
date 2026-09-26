from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from yutto.cli.auth import resolve_auth_command_options
from yutto.cli.compat import normalize_argv
from yutto.cli.credentials import resolve_credential_options
from yutto.cli.input import apply_cli_overrides, expand_download_configs
from yutto.cli.parser import build_parser
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.settings import YuttoConfig, resolved_config_from_settings
from yutto.config import DEFAULT_CONFIG, ResolvedConfig

if TYPE_CHECKING:
    from pathlib import Path


def test_resolved_config_preserves_explicit_none_without_parent_lookup():
    configured = replace(
        DEFAULT_CONFIG,
        network=replace(DEFAULT_CONFIG.network, proxy="config"),
        output=replace(DEFAULT_CONFIG.output, temporary_directory=Path("config")),
    )
    cli = replace(
        configured,
        network=replace(configured.network, proxy="cli"),
        output=replace(configured.output, temporary_directory=None),
    )

    assert cli.network.proxy == "cli"
    assert cli.output.temporary_directory is None
    assert cli.stream.video_quality == 127


def test_persistent_config_maps_into_typed_specs():
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
    assert resolved.danmaku.font_size == 36
    assert resolved.selection.published_since is not None
    assert resolved.credential.profile == "work"
    assert config.basic.ffmpeg_path == "/opt/ffmpeg"


def test_no_inherit_cuts_outer_cli_config_but_keeps_persistent_config(tmp_path: Path):
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
    settings = YuttoConfig.model_validate({"basic": {"proxy": "config-proxy"}})
    configured = resolved_config_from_settings(settings)
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
    outer, no_inherit = apply_cli_overrides(configured, raw)

    first, second = expand_download_configs(
        outer,
        parser,
        configured,
        no_inherit=no_inherit,
    )

    assert first.network.proxy == "no"
    assert first.network.fetch_workers == 2
    assert second.network.proxy == "config-proxy"
    assert second.network.fetch_workers == 5


def test_runtime_controls_stay_outside_resolved_task_config():
    settings = YuttoConfig.model_validate(
        {
            "basic": {
                "jobs": 3,
                "proxy": "config-proxy",
                "ffmpeg_path": "/config/ffmpeg",
            },
            "auth": {"auth_profile": "config-profile"},
        }
    )
    configured = resolved_config_from_settings(settings)
    values = {
        "source": "BV1xx411c7mD",
        "jobs": 5,
        "proxy": "no",
        "download_vcodec_priority": None,
        "auth_profile": "cli-profile",
    }
    task, _ = apply_cli_overrides(configured, values)

    runtime = resolve_runtime_options(values, settings)
    credentials = resolve_credential_options([task])[0]

    assert task.network.proxy == "no"
    assert task.stream.video_codec_priority is None
    assert runtime.jobs == 5
    assert runtime.ffmpeg_path == "/config/ffmpeg"
    assert credentials.auth_profile == "cli-profile"


def test_auth_command_combines_resolved_task_config_and_command_controls():
    settings = YuttoConfig.model_validate(
        {
            "basic": {"proxy": "config-proxy"},
            "auth": {
                "auth": "SESSDATA=config",
                "auth_profile": "config-profile",
            },
        }
    )
    configured = resolved_config_from_settings(settings)
    task, _ = apply_cli_overrides(configured, {"auth_profile": "cli-profile"})

    options = resolve_auth_command_options(task, "login", {"mode": "web"})

    assert options.auth_command == "login"
    assert options.auth == "SESSDATA=config"
    assert options.auth_profile == "cli-profile"
    assert options.proxy == "config-proxy"
    assert options.mode == "web"
    assert options.poll_interval == 2.0
    assert options.timeout == 180


def test_empty_settings_use_spec_and_runtime_defaults():
    settings = YuttoConfig()
    configured = resolved_config_from_settings(settings)
    task, _ = apply_cli_overrides(configured, {"source": "BV1xx411c7mD"})

    runtime = resolve_runtime_options({}, settings)

    assert isinstance(task, ResolvedConfig)
    assert task.network.download_workers == 8
    assert task.stream.video_quality == 127
    assert runtime.jobs == 1
    assert runtime.ffmpeg_path is None
