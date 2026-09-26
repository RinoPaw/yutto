from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

import yutto.server.command as server_command_module
from yutto.api.player import get_subtitle_lines
from yutto.cli.parser import build_parser
from yutto.cli.settings import YuttoConfig
from yutto.config import DEFAULT_CONFIG, ResolvedConfig
from yutto.exceptions import ApiResponseError, NoAccessPermissionError
from yutto.source import AmbiguousEpisodeSource, BangumiEpisodeSource, CheeseEpisodeSource, MediaResolveResult
from yutto.types import EpisodeId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.media import Media

_EXECUTION = cast("ExecutionScope", None)
_CONFIG = DEFAULT_CONFIG


def test_ambiguous_source_does_not_hide_unexpected_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve_bangumi(
        self: BangumiEpisodeSource,
        execution: ExecutionScope,
        config: ResolvedConfig,
    ) -> MediaResolveResult[Media]:
        return MediaResolveResult(media=cast("Media", object()))

    async def resolve_cheese(
        self: CheeseEpisodeSource,
        execution: ExecutionScope,
        config: ResolvedConfig,
    ) -> MediaResolveResult[Media]:
        raise NoAccessPermissionError("cheese probe failed")

    monkeypatch.setattr(BangumiEpisodeSource, "resolve", resolve_bangumi)
    monkeypatch.setattr(CheeseEpisodeSource, "resolve", resolve_cheese)

    with pytest.raises(NoAccessPermissionError, match="cheese probe failed"):
        asyncio.run(AmbiguousEpisodeSource(id=EpisodeId("123")).resolve(_EXECUTION, _CONFIG))


def test_malformed_player_response_has_protocol_error_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fetch_json(*args: Any, **kwargs: Any) -> Success[dict[str, object]]:
        return Success({"body": "invalid"})

    monkeypatch.setattr("yutto.api.player.Fetcher.fetch_json", fetch_json)

    with pytest.raises(ApiResponseError):
        asyncio.run(get_subtitle_lines(_EXECUTION, "https://example.invalid/subtitle.json"))


def test_serve_uses_configured_ffmpeg_path(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[str] = []

    class RecordingFFmpeg:
        @classmethod
        def setup_ffmpeg_path(cls, ffmpeg_path: str) -> None:
            recorded.append(ffmpeg_path)
            raise RuntimeError("stop after recording")

    monkeypatch.setattr(server_command_module, "FFmpeg", RecordingFFmpeg)
    args = build_parser().parse_args(["serve"])
    settings = YuttoConfig.model_validate({"basic": {"ffmpeg_path": "/config/ffmpeg"}})

    with pytest.raises(RuntimeError, match="stop after recording"):
        server_command_module.run_server_command(args, settings)

    assert recorded == ["/config/ffmpeg"]
