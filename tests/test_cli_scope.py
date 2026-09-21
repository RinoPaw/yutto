from __future__ import annotations

from pathlib import Path

from yutto.cli.compat import normalize_argv
from yutto.cli.credentials import resolve_credential_options
from yutto.cli.input import expand_download_scopes
from yutto.cli.parser import build_parser
from yutto.cli.request_adapter import resolve_download_request
from yutto.cli.runtime import resolve_runtime_options
from yutto.cli.scope import MISSING, Scope, config_scope
from yutto.cli.settings import YuttoConfig


def test_scope_uses_lexical_shadowing_and_preserves_explicit_none():
    configured = Scope({"value": "config", "cleared": "config"})
    cli = Scope({"value": "cli", "cleared": None}, parent=configured)

    assert cli.lookup("value") == "cli"
    assert cli.lookup("cleared") is None
    assert cli.lookup("missing") is MISSING


def test_config_scope_maps_persistent_names_to_cli_namespace():
    config = YuttoConfig.model_validate(
        {
            "basic": {
                "num_workers": 12,
                "metadata_format_premiered": "%Y-%m-%d",
                "ffmpeg_path": "/opt/ffmpeg",
            },
            "danmaku": {"font_size": 36},
            "batch": {"batch_filter_start_time": "2026-01-01"},
            "auth": {"auth_profile": "work"},
        }
    )

    scope = config_scope(config)

    assert scope.lookup("download_workers") == 12
    assert scope.lookup("metadata_premiered_format") == "%Y-%m-%d"
    assert scope.lookup("ffmpeg_path") == "/opt/ffmpeg"
    assert scope.lookup("danmaku_font_size") == 36
    assert scope.lookup("publication_start_time") == "2026-01-01"
    assert scope.lookup("auth_profile") == "work"


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
    configured = config_scope(config)
    outer = Scope(
        vars(
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
        ),
        parent=configured,
    )

    first, second = expand_download_scopes(outer, parser, configured)

    assert first.lookup("proxy") == "no"
    assert first.lookup("fetch_workers") == 2
    assert second.lookup("proxy") == "config-proxy"
    assert second.lookup("fetch_workers") == 5


def test_scope_feeds_request_runtime_and_credentials_from_one_chain():
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
    configured = config_scope(config)
    cli = Scope(
        {
            "source": "BV1xx411c7mD",
            "jobs": 5,
            "proxy": "no",
            "download_vcodec_priority": None,
            "auth_profile": "cli-profile",
        },
        parent=configured,
    )

    request = resolve_download_request(cli)
    runtime = resolve_runtime_options(cli)
    credentials = resolve_credential_options([cli])[0]

    assert request.network.proxy == "no"
    assert request.stream.video_download_codec_priority is None
    assert runtime.jobs == 5
    assert runtime.ffmpeg_path == "/config/ffmpeg"
    assert credentials.auth_profile == "cli-profile"


def test_empty_scope_leaves_owned_defaults_to_lower_layers():
    configured = config_scope(YuttoConfig())
    cli = Scope({"source": "BV1xx411c7mD"}, parent=configured)

    request = resolve_download_request(cli)
    runtime = resolve_runtime_options(cli)

    assert request.network.download_workers == 8
    assert request.stream.video_quality == 127
    assert runtime.jobs is None
    assert runtime.ffmpeg_path is None
