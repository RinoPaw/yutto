from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto._native import InvalidUrlError, UnsupportedProtocolError
from yutto.exceptions import WrongUrlError
from yutto.parser import parse
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


async def parse_input(scope: ExecutionScope, request: DownloadRequest) -> ParsedInput:
    """Parse one request input, following a redirect only when pure parsing cannot identify it."""
    value = request.source.url.strip()

    if source := parse(value):
        return ParsedInput(value=value, source=source)

    try:
        redirected_value = unwrap_fetch_result(await Fetcher.get_redirected_url(scope, value))
    except InvalidUrlError:
        raise WrongUrlError(f"无效的 url({value})～请检查一下链接是否正确～") from None
    except UnsupportedProtocolError:
        raise WrongUrlError(f"无效的 url 协议（{value}）～请检查一下链接协议是否正确") from None

    if source := parse(redirected_value):
        return ParsedInput(value=redirected_value, source=source)
    raise WrongUrlError(f"无法识别 url（{redirected_value}）")
