from __future__ import annotations

from typing import TYPE_CHECKING

from yutto.auth import validate_user_info
from yutto.utils.console.logger import Badge, Logger

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.core.request import DownloadRequest


class CliAuthAnnouncer:
    """Announce each effective credential once without sharing request caches."""

    def __init__(self):
        self._announced_credentials: set[tuple[str | None, str | None]] = set()

    async def __call__(self, scope: ExecutionScope, request: DownloadRequest) -> None:
        credentials = (
            scope.session.cookie("SESSDATA"),
            scope.session.cookie("bili_jct"),
        )
        if credentials in self._announced_credentials:
            return
        self._announced_credentials.add(credentials)
        await announce_cli_auth(scope, request)


async def announce_cli_auth(scope: ExecutionScope, _request: DownloadRequest) -> None:
    if scope.session.cookie("SESSDATA") is None:
        Logger.info(
            "未提供登录认证信息，无法下载高清视频、字幕等资源哦～请通过 `--auth` 参数提供认证信息，或者先使用 `yutto auth login` 登录存储认证信息后再下载～"
        )
        return
    if await validate_user_info(scope, {"vip_status": True, "is_login": True}):
        Logger.custom("成功以大会员身份登录～", badge=Badge("大会员", fore="white", back="magenta", style=["bold"]))
    else:
        Logger.warning("以非大会员身份登录，注意无法下载会员专享剧集喔～")
