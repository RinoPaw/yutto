from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto._native import InvalidUrlError, UnsupportedProtocolError
from yutto.exceptions import WrongUrlError
from yutto.parser import ParseOptions, parse
from yutto.source import SourceOptions
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.core.request import DownloadRequest
    from yutto.source import Source


@dataclass(frozen=True, slots=True)
class ParsedInput:
    """One recognized input and the exact value that Parser recognized."""

    value: str
    source: Source


def parse_options_from_request(request: DownloadRequest) -> ParseOptions:
    """Translate one core request into the options visible to the Parser and Source layers."""
    return ParseOptions(
        selection=request.selection.episodes,
        source_options=SourceOptions(
            with_extra_episodes=request.scope.with_extra_episodes,
            skip_preview=request.selection.skip_preview,
            require_metadata=request.resources.metadata,
        ),
    )


async def parse_input(scope: ExecutionScope, request: DownloadRequest) -> ParsedInput:
    """Parse one request input, following a redirect only when pure parsing cannot identify it."""
    value = request.source.url.strip()
    options = parse_options_from_request(request)

    if source := parse(value, options):
        return ParsedInput(value=value, source=source)

    try:
        redirected_value = unwrap_fetch_result(await Fetcher.get_redirected_url(scope, value))
    except InvalidUrlError:
        raise WrongUrlError(f"无效的 url({value})～请检查一下链接是否正确～") from None
    except UnsupportedProtocolError:
        raise WrongUrlError(f"无效的 url 协议（{value}）～请检查一下链接协议是否正确") from None

    if source := parse(redirected_value, options):
        return ParsedInput(value=redirected_value, source=source)
    raise WrongUrlError(f"无法识别 url（{redirected_value}）")
