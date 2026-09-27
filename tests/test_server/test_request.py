from __future__ import annotations

import pytest

from yutto.cli.settings import YuttoConfig
from yutto.server.request import config_parser_from_settings

pytestmark = pytest.mark.processor


def test_request_rejects_null_for_non_nullable_override():
    parse = config_parser_from_settings(YuttoConfig())

    with pytest.raises(ValueError, match="invalid request field: access.login_strict"):
        parse(
            {
                "source": {"url": "BV1server"},
                "access": {"login_strict": None},
            }
        )


def test_request_allows_null_for_nullable_override():
    settings = YuttoConfig.model_validate({"basic": {"banned_mirrors_pattern": "configured-mirror"}})
    parse = config_parser_from_settings(settings)

    config = parse(
        {
            "source": {"url": "BV1server"},
            "network": {"banned_mirrors_pattern": None},
        }
    )

    assert config.network.banned_mirrors_pattern is None


def test_request_maps_fixed_danmaku_blocking():
    parse = config_parser_from_settings(YuttoConfig())

    config = parse(
        {
            "source": {"url": "BV1server"},
            "danmaku": {"block_fixed": True},
        }
    )

    assert config.danmaku.block_fixed is True
