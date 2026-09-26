from __future__ import annotations

from typing import TYPE_CHECKING

from yutto._native import InvalidUrlError, UnsupportedProtocolError
from yutto.exceptions import WrongUrlError
from yutto.parser import parse
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.source import MediaSource


async def resolve_redirected_source(scope: ExecutionScope, value: str) -> MediaSource:
    try:
        redirected_value = unwrap_fetch_result(await Fetcher.get_redirected_url(scope, value))
    except InvalidUrlError:
        raise WrongUrlError(f"无效的 url({value})～请检查一下链接是否正确～") from None
    except UnsupportedProtocolError:
        raise WrongUrlError(f"无效的 url 协议（{value}）～请检查一下链接协议是否正确") from None

    source = parse(redirected_value)
    if source is None:
        raise WrongUrlError(f"无法识别 url（{redirected_value}）")
    return source


__all__ = ["resolve_redirected_source"]
