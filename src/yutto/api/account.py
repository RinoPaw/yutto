from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import string
import time
import urllib.parse
from typing import TYPE_CHECKING, Any, TypedDict, cast

from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto._native import YuttoSession
    from yutto.core.execution import ExecutionScope

NAV_API = "https://api.bilibili.com/x/web-interface/nav"
QR_GENERATE_API = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_API = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


class WbiImg(TypedDict):
    img_key: str
    sub_key: str


dm_img_str_cache = base64.b64encode("".join(random.choices(string.printable, k=random.randint(16, 64))).encode())[
    :-2
].decode()
dm_cover_img_str_cache = base64.b64encode(
    "".join(random.choices(string.printable, k=random.randint(32, 128))).encode()
)[:-2].decode()


async def request_json(session: YuttoSession, url: str, *, params: dict[str, str]) -> dict[str, Any]:
    resp = await session.get(url, params=list(params.items()))
    resp.raise_for_status()
    payload_any = json.loads(resp.body)
    if not isinstance(payload_any, dict):
        raise ValueError(f"接口返回 JSON 结构异常：{url}")
    return cast("dict[str, Any]", payload_any)


async def generate_qr_login(session: YuttoSession) -> tuple[str, str]:
    payload = await request_json(session, QR_GENERATE_API, params={"source": "main-fe-header"})
    code = payload.get("code")
    if not isinstance(code, int) or code != 0:
        raise ValueError(f"获取登录二维码失败：{payload}")
    data_any = payload.get("data")
    if not isinstance(data_any, dict):
        raise ValueError(f"获取登录二维码失败，返回值异常：{payload}")
    data = cast("dict[str, Any]", data_any)
    login_url = data.get("url")
    qrcode_key = data.get("qrcode_key")
    if not isinstance(login_url, str) or not isinstance(qrcode_key, str):
        raise ValueError(f"获取登录二维码失败，缺少 url 或 qrcode_key：{payload}")
    return login_url, qrcode_key


async def follow_login_redirect(session: YuttoSession, redirect_url: str) -> str:
    return (await session.get(redirect_url)).url


async def get_nav(scope: ExecutionScope) -> dict[str, Any]:
    if scope.nav_cache is not None:
        return scope.nav_cache
    async with scope.nav_lock:
        if scope.nav_cache is None:
            scope.nav_cache = unwrap_fetch_result(await Fetcher.fetch_json(scope, NAV_API))
        return scope.nav_cache


async def get_wbi_img(scope: ExecutionScope) -> WbiImg:
    res_json = await get_nav(scope)
    return WbiImg(
        img_key=_get_key_from_url(res_json["data"]["wbi_img"]["img_url"]),
        sub_key=_get_key_from_url(res_json["data"]["wbi_img"]["sub_url"]),
    )


def _get_key_from_url(url: str) -> str:
    return url.split("/")[-1].split(".")[0]


def _get_mixin_key(value: str) -> str:
    char_indices = [
        46,
        47,
        18,
        2,
        53,
        8,
        23,
        32,
        15,
        50,
        10,
        31,
        58,
        3,
        45,
        35,
        27,
        43,
        5,
        49,
        33,
        9,
        42,
        19,
        29,
        28,
        14,
        39,
        12,
        38,
        41,
        13,
        37,
        48,
        7,
        16,
        24,
        55,
        40,
        61,
        26,
        17,
        0,
        1,
        60,
        51,
        30,
        4,
        22,
        25,
        54,
        21,
        56,
        59,
        6,
        63,
        57,
        62,
        11,
        36,
        20,
        34,
        44,
        52,
    ]
    return "".join(value[index] for index in char_indices[:32])


def encode_wbi(params: dict[str, Any], wbi_img: WbiImg) -> dict[str, Any]:
    illegal_char_remover = re.compile(r"[!'\(\)*]")
    mixin_key = _get_mixin_key(wbi_img["img_key"] + wbi_img["sub_key"])
    params_with_dm = {
        **params,
        "wts": int(time.time()),
        "dm_img_list": "[]",
        "dm_img_str": dm_img_str_cache,
        "dm_cover_img_str": dm_cover_img_str_cache,
    }
    url_encoded_params = urllib.parse.urlencode(
        {key: illegal_char_remover.sub("", str(params_with_dm[key])) for key in sorted(params_with_dm)}
    )
    return {
        **params_with_dm,
        "w_rid": hashlib.md5((url_encoded_params + mixin_key).encode()).hexdigest(),
    }


__all__ = [
    "NAV_API",
    "QR_GENERATE_API",
    "QR_POLL_API",
    "WbiImg",
    "dm_cover_img_str_cache",
    "dm_img_str_cache",
    "encode_wbi",
    "follow_login_redirect",
    "generate_qr_login",
    "get_nav",
    "get_wbi_img",
    "request_json",
]
