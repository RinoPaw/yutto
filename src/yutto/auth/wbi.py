from __future__ import annotations

import base64
import hashlib
import random
import re
import string
import time
import urllib.parse
from typing import TYPE_CHECKING, Any, TypedDict

from yutto.api.common import get_nav

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope


class WbiImg(TypedDict):
    img_key: str
    sub_key: str


dm_img_str_cache = base64.b64encode("".join(random.choices(string.printable, k=random.randint(16, 64))).encode())[
    :-2
].decode()
dm_cover_img_str_cache = base64.b64encode(
    "".join(random.choices(string.printable, k=random.randint(32, 128))).encode()
)[:-2].decode()


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


__all__ = ["WbiImg", "dm_cover_img_str_cache", "dm_img_str_cache", "encode_wbi", "get_wbi_img"]
