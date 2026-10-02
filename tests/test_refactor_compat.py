from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.api.ugc import get_ugc_video_info
from yutto.cli.settings import YuttoConfig, resolved_config_from_settings
from yutto.types import BvId
from yutto.utils.time import parse_local_timestamp

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

pytestmark = pytest.mark.processor


def test_legacy_yutto_toml_names_resolve_into_typed_config() -> None:
    settings = YuttoConfig.model_validate(
        {
            "basic": {
                "num_workers": 12,
                "metadata_format_premiered": "%Y/%m/%d",
            },
            "danmaku": {
                "font_size": 42,
                "font": "LegacyFont",
                "opacity": 0.5,
                "display_region_ratio": 0.75,
                "speed": 1.25,
                "block_top": True,
                "block_bottom": True,
                "block_scroll": True,
                "block_reverse": True,
                "block_fixed": True,
                "block_special": True,
                "block_colorful": True,
                "block_keyword_patterns": ["foo", "bar"],
            },
            "batch": {
                "batch_filter_start_time": "2024-01-02",
                "batch_filter_end_time": "2024-02-03",
            },
        }
    )

    config = resolved_config_from_settings(settings)

    assert config.network.download_workers == 12
    assert config.output.metadata_premiered_format == "%Y/%m/%d"
    assert config.danmaku.font_size == 42
    assert config.danmaku.font == "LegacyFont"
    assert config.danmaku.opacity == 0.5
    assert config.danmaku.display_region_ratio == 0.75
    assert config.danmaku.speed == 1.25
    assert config.danmaku.block_top is True
    assert config.danmaku.block_bottom is True
    assert config.danmaku.block_scroll is True
    assert config.danmaku.block_reverse is True
    assert config.danmaku.block_fixed is True
    assert config.danmaku.block_special is True
    assert config.danmaku.block_colorful is True
    assert config.danmaku.block_keyword_patterns == ("foo", "bar")
    assert config.selection.published_since == parse_local_timestamp("2024-01-02")
    assert config.selection.published_before == parse_local_timestamp("2024-02-03")


def test_ugc_decoder_normalizes_meaningless_page_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_json(_execution: object, _url: str, **_kwargs: Any) -> Success[dict[str, Any]]:
        return Success(
            {
                "code": 0,
                "data": {
                    "aid": 808982399,
                    "bvid": "BV1D84y1t76J",
                    "title": "投稿",
                    "desc": "简介",
                    "pic": "https://img/cover.jpg",
                    "pubdate": 1700000000,
                    "pages": [
                        {"cid": 101, "part": ""},
                        {"cid": 102, "part": "source.mp4"},
                        {"cid": 103, "part": "正常分P"},
                    ],
                },
            }
        )

    monkeypatch.setattr("yutto.utils.fetcher.Fetcher.fetch_json", fake_fetch_json)
    info = asyncio.run(
        get_ugc_video_info(
            cast("ExecutionScope", None),
            BvId("BV1D84y1t76J"),
        )
    )

    assert [page.title for page in info.pages] == ["投稿_P01", "投稿_P02", "正常分P"]
