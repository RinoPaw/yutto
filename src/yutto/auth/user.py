from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from yutto.types import UserInfo
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope

USER_INFO_API = "https://api.bilibili.com/x/web-interface/nav"


def parse_user_info(res_json: dict[str, Any]) -> UserInfo:
    res_json_data_any = res_json.get("data")
    if not isinstance(res_json_data_any, dict):
        raise ValueError(f"获取用户信息失败，返回值异常：{res_json}")
    res_json_data = cast("dict[str, Any]", res_json_data_any)
    return UserInfo(
        vip_status=res_json_data.get("vipStatus") == 1,
        is_login=bool(res_json_data.get("isLogin")),
    )


async def get_user_info(scope: ExecutionScope) -> UserInfo:
    if scope.user_info_cache is not None:
        return scope.user_info_cache
    async with scope.user_info_lock:
        if scope.user_info_cache is None:
            res_json = unwrap_fetch_result(await Fetcher.fetch_json(scope, USER_INFO_API))
            scope.user_info_cache = parse_user_info(res_json)
        return scope.user_info_cache


def user_info_matches(user_info: UserInfo, check_option: UserInfo) -> bool:
    if check_option["is_login"] and not user_info["is_login"]:
        return False
    if check_option["vip_status"] and not user_info["vip_status"]:
        return False
    return True


async def validate_user_info(scope: ExecutionScope, check_option: UserInfo) -> bool:
    if not check_option["is_login"] and not check_option["vip_status"]:
        return True
    if scope.user_info_cache is not None:
        return user_info_matches(scope.user_info_cache, check_option)
    return user_info_matches(await get_user_info(scope), check_option)


__all__ = ["USER_INFO_API", "get_user_info", "parse_user_info", "user_info_matches", "validate_user_info"]
