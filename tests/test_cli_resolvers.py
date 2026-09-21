from __future__ import annotations

from pathlib import Path

from yutto.cli.credentials import resolve_credential_options
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.settings import YuttoConfig, resolve_config


def test_runtime_options_leave_lower_layer_defaults_unresolved():
    runtime = resolve_runtime_options({}, YuttoConfig())

    assert runtime.jobs is None
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


def test_credential_options_merge_task_over_config(tmp_path: Path):
    config_auth_file = tmp_path / "config-auth.toml"
    cli_auth_file = tmp_path / "cli-auth.toml"
    config = YuttoConfig.model_validate(
        {
            "basic": {"sessdata": "config-sessdata"},
            "auth": {
                "auth": "config-auth",
                "auth_file": str(config_auth_file),
                "auth_profile": "config-profile",
            },
        }
    )

    options = resolve_credential_options(
        [
            {"source": "BV1config"},
            {
                "source": "BV1cli",
                "auth": "cli-auth",
                "auth_file": cli_auth_file,
                "auth_profile": "cli-profile",
                "sessdata": "cli-sessdata",
            },
        ],
        config,
    )

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
