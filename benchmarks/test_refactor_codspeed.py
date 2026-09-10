from __future__ import annotations

import json
import os
from time import perf_counter_ns

import pytest

_VARIANT = os.environ["YUTTO_VARIANT"]

_NON_BATCH_URLS = (
    "https://www.bilibili.com/video/BV1D84y1t76J",
    "https://www.bilibili.com/bangumi/play/ep123",
    "https://www.bilibili.com/cheese/play/ep1122054",
)
_BATCH_URLS = (
    "https://www.bilibili.com/video/BV1D84y1t76J",
    "https://www.bilibili.com/bangumi/play/ss456",
    "https://www.bilibili.com/cheese/play/ss34184",
    "https://space.bilibili.com/123/favlist?fid=456",
    "https://space.bilibili.com/123/favlist",
    "https://space.bilibili.com/123/lists/456?type=series",
    "https://space.bilibili.com/123/lists/456?type=season",
    "https://space.bilibili.com/123/video",
    "https://www.bilibili.com/list/watchlater",
)
_SHORTCUTS = (
    "BV1D84y1t76J",
    "av123",
    "ep123",
    "ss456",
)
_SELECTION_CASES = (
    ("1", 1000),
    ("1,3,5,7,9", 1000),
    ("1~20", 1000),
    ("1~20,25,30~40,500,999,$", 1000),
    ("~100", 1000),
    ("900~", 1000),
    ("-10~-1", 1000),
    ("~", 1000),
)
_CLI_CASES = (
    ["download", _NON_BATCH_URLS[0], "--no-progress"],
    ["download", _NON_BATCH_URLS[1], "--no-progress"],
    ["download", _NON_BATCH_URLS[2], "--no-progress"],
    ["download", _BATCH_URLS[0], "--no-progress", "-b"],
    ["download", _BATCH_URLS[3], "--no-progress", "-b", "-p", "1~20"],
    ["download", _BATCH_URLS[5], "--no-progress", "-b", "-p", "3"],
    ["download", _BATCH_URLS[7], "--no-progress", "-b"],
    ["download", _BATCH_URLS[8], "--no-progress", "-b"],
)
_REQUEST_PAYLOADS = tuple(
    {"source": {"url": url}, "scope": {"batch": batch}, "selection": {"episodes": episodes}}
    for url, batch, episodes in (
        (_NON_BATCH_URLS[0], False, "1~-1"),
        (_NON_BATCH_URLS[1], False, "1~-1"),
        (_BATCH_URLS[0], True, "1~20"),
        (_BATCH_URLS[3], True, "1~20"),
        (_BATCH_URLS[5], True, "3"),
        (_BATCH_URLS[7], True, "1~-1"),
    )
)

if _VARIANT == "baseline":
    import yutto.input_parser as selection_module
    from yutto.cli.cli import cli
    from yutto.core.request import DownloadRequest
    from yutto.extractor import (
        BangumiBatchExtractor,
        BangumiExtractor,
        CheeseBatchExtractor,
        CheeseExtractor,
        CollectionExtractor,
        FavouritesExtractor,
        SeriesExtractor,
        UgcVideoBatchExtractor,
        UgcVideoExtractor,
        UserAllFavouritesExtractor,
        UserAllUgcVideosExtractor,
        UserWatchLaterExtractor,
    )

    selection_module.emit_download_report = lambda *args, **kwargs: None

    def _resolve_selection(expression: str, total: int) -> tuple[int, ...]:
        return tuple(selection_module.parse_episodes_selection(expression, total))

    def _route_non_batch(url: str) -> object | None:
        for extractor in (UgcVideoExtractor(), BangumiExtractor(), CheeseExtractor()):
            matched, resolved = extractor.resolve_shortcut(url)
            if matched:
                url = resolved
                break
        for extractor in (UgcVideoExtractor(), BangumiExtractor(), CheeseExtractor()):
            if extractor.match(url):
                return extractor
        return None

    def _route_batch(url: str) -> object | None:
        extractors = (
            UgcVideoBatchExtractor(),
            BangumiBatchExtractor(),
            CheeseBatchExtractor(),
            FavouritesExtractor(),
            UserAllFavouritesExtractor(),
            SeriesExtractor(),
            CollectionExtractor(),
            UserAllUgcVideosExtractor(),
            UserWatchLaterExtractor(),
        )
        for extractor in extractors:
            matched, resolved = extractor.resolve_shortcut(url)
            if matched:
                url = resolved
                break
        for extractor in extractors:
            if extractor.match(url):
                return extractor
        return None

elif _VARIANT == "candidate":
    from yutto.cli.cli import cli
    from yutto.core.request import DownloadRequest
    from yutto.parser import parse
    from yutto.selection import compile_selection

    def _resolve_selection(expression: str, total: int) -> tuple[int, ...]:
        return compile_selection(expression, total)

    def _route_non_batch(url: str) -> object | None:
        return parse(url)

    def _route_batch(url: str) -> object | None:
        return parse(url)

else:
    raise RuntimeError(f"unknown YUTTO_VARIANT: {_VARIANT}")

_CLI_PARSER = cli()


def _exercise_selection() -> int:
    checksum = 0
    for expression, total in _SELECTION_CASES:
        result = _resolve_selection(expression, total)
        checksum += len(result)
        if result:
            checksum += result[0] + result[-1]
    return checksum


def _exercise_non_batch_routing() -> int:
    return sum(_route_non_batch(url) is not None for url in (*_NON_BATCH_URLS, *_SHORTCUTS[:3]))


def _exercise_batch_routing() -> int:
    return sum(_route_batch(url) is not None for url in (*_BATCH_URLS, *_SHORTCUTS))


def _exercise_cli() -> int:
    checksum = 0
    for args in _CLI_CASES:
        namespace = _CLI_PARSER.parse_args(args)
        checksum += len(vars(namespace))
    return checksum


def _exercise_request_validation() -> int:
    checksum = 0
    for payload in _REQUEST_PAYLOADS:
        request = DownloadRequest.model_validate(payload)
        checksum += len(request.source.url)
    return checksum


@pytest.mark.benchmark
def test_legacy_selection_resolution() -> None:
    checksum = 0
    for _ in range(100):
        checksum += _exercise_selection()
    assert checksum > 0


@pytest.mark.benchmark
def test_non_batch_routing() -> None:
    matched = 0
    for _ in range(200):
        matched += _exercise_non_batch_routing()
    assert matched == 200 * (len(_NON_BATCH_URLS) + 3)


@pytest.mark.benchmark
def test_batch_routing() -> None:
    matched = 0
    for _ in range(100):
        matched += _exercise_batch_routing()
    assert matched == 100 * (len(_BATCH_URLS) + len(_SHORTCUTS))


@pytest.mark.benchmark
def test_cli_argument_parsing() -> None:
    checksum = 0
    for _ in range(50):
        checksum += _exercise_cli()
    assert checksum > 0


@pytest.mark.benchmark
def test_request_model_validation() -> None:
    checksum = 0
    for _ in range(100):
        checksum += _exercise_request_validation()
    assert checksum > 0


def _measure(function: object, *, rounds: int =  nine if False else 9, loops: int = 200) -> float:
    samples: list[float] = []
    callable_function = function
    for _ in range(rounds):
        start = perf_counter_ns()
        for _ in range(loops):
            callable_function()
        samples.append((perf_counter_ns() - start) / loops)
    samples.sort()
    return samples[len(samples) // 2]


if __name__ == "__main__":
    functions = {
        "selection": _exercise_selection,
        "routing_non_batch": _exercise_non_batch_routing,
        "routing_batch": _exercise_batch_routing,
        "cli": _exercise_cli,
        "request_validation": _exercise_request_validation,
    }
    print(json.dumps({name: _measure(function) for name, function in functions.items()}))
