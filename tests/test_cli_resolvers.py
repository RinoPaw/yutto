from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from yutto.cli.credentials import resolve_credential_options
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.settings import YuttoConfig, resolve_config, resolved_config_from_settings

if TYPE_CHECKING:
    from pathlib import Path


def test_runtime_options_use_process_defaults():
    runtime = resolve_runtime_options({}, YuttoConfig())

    assert runtime.jobs == 1
    assert runtime.ffmpeg_path is None


def test_runtime_options_resolve_preview_mode():
    config = YuttoConfig()

    assert resolve_runtime_options({}, config).preview_formats is False
    assert resolve_runtime_options({"preview_formats": True}, config).preview_formats is True


def test_runtime_options_merge_cli_over_config():
    config = YuttoConfig.model_validate(
        {
            "basic": {
                "jobs": 3,
                "ffmpeg_path": "/config/ffmpeg",
                "no_progress": True,
            }
        }
    )

    runtime = resolve_runtime_options(
        {
            "jobs": 5,
            "ffmpeg_path": "/cli/ffmpeg",
        },
        config,
    )

    assert runtime.jobs == 5
    assert runtime.ffmpeg_path == "/cli/ffmpeg"
    assert runtime.no_progress is True


def test_resolve_config_loads_explicit_path(tmp_path: Path):
    config_path = tmp_path / "yutto.toml"
    config_path.write_text('[basic]\njobs = 3\nffmpeg_path = "/opt/ffmpeg"\n', encoding="utf-8")

    config = resolve_config(config_path)

    assert config.basic.jobs == 3
    assert config.basic.ffmpeg_path == "/opt/ffmpeg"


def test_resolve_config_uses_injected_search(tmp_path: Path):
    config_path = tmp_path / "yutto.toml"
    config_path.write_text("[basic]\nno_progress = true\n", encoding="utf-8")

    config = resolve_config(search=lambda: config_path)

    assert config.basic.no_progress is True


def test_credential_options_project_each_resolved_task_config(tmp_path: Path):
    config_auth_file = tmp_path / "config-auth.toml"
    cli_auth_file = tmp_path / "cli-auth.toml"
    settings = YuttoConfig.model_validate(
        {
            "basic": {"sessdata": "config-sessdata"},
            "auth": {
                "auth": "config-auth",
                "auth_file": str(config_auth_file),
                "auth_profile": "config-profile",
            },
        }
    )
    configured = resolved_config_from_settings(settings)
    cli = replace(
        configured,
        credential=replace(
            configured.credential,
            cookie="cli-auth",
            file=cli_auth_file,
            profile="cli-profile",
            sessdata="cli-sessdata",
        ),
    )

    options = resolve_credential_options([configured, cli])

    assert vars(options[0]) == {
        "auth": "config-auth",
        "auth_file": config_auth_file,
        "auth_profile": "config-profile",
        "sessdata": "config-sessdata",
    }
    assert vars(options[1]) == {
        "auth": "cli-auth",
        "auth_file": cli_auth_file,
        "auth_profile": "cli-profile",
        "sessdata": "cli-sessdata",
    }
