from __future__ import annotations

import base64
import hashlib
import os
import platform
import random
import re
import string
import time
import tomllib
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, cast

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from yutto.types import UserInfo
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from argparse import Namespace

    from yutto.core.execution import ExecutionScope

PROFILE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
USER_INFO_API = "https://api.bilibili.com/x/web-interface/nav"


class AuthInfo(TypedDict):
    SESSDATA: str
    bili_jct: str | None


class WbiImg(TypedDict):
    img_key: str
    sub_key: str


dm_img_str_cache = base64.b64encode(
    "".join(random.choices(string.printable, k=random.randint(16, 64))).encode()
)[:-2].decode()
dm_cover_img_str_cache = base64.b64encode(
    "".join(random.choices(string.printable, k=random.randint(32, 128))).encode()
)[:-2].decode()


class AuthProfileModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    sessdata: str = Field(validation_alias=AliasChoices("sessdata", "SESSDATA"))
    bili_jct: str | None = None
    updated_at: str | None = None


class AuthFileModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    profiles: dict[str, AuthProfileModel] = Field(default_factory=dict)


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


async def get_wbi_img(scope: ExecutionScope) -> WbiImg:
    if scope.wbi_img_cache is not None:
        return cast("WbiImg", scope.wbi_img_cache)
    async with scope.wbi_img_lock:
        if scope.wbi_img_cache is None:
            res_json = unwrap_fetch_result(await Fetcher.fetch_json(scope, USER_INFO_API))
            wbi_img = WbiImg(
                img_key=_get_key_from_url(res_json["data"]["wbi_img"]["img_url"]),
                sub_key=_get_key_from_url(res_json["data"]["wbi_img"]["sub_url"]),
            )
            scope.wbi_img_cache = cast("dict[str, str]", dict(wbi_img))
        return cast("WbiImg", scope.wbi_img_cache)


def _get_key_from_url(url: str) -> str:
    return url.split("/")[-1].split(".")[0]


def _get_mixin_key(value: str) -> str:
    char_indices = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5,
        49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55,
        40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57,
        62, 11, 36, 20, 34, 44, 52,
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
        {
            key: illegal_char_remover.sub("", str(params_with_dm[key]))
            for key in sorted(params_with_dm)
        }
    )
    return {
        **params_with_dm,
        "w_rid": hashlib.md5((url_encoded_params + mixin_key).encode()).hexdigest(),
    }


def xdg_config_home() -> Path:
    if (env := os.environ.get("XDG_CONFIG_HOME")) and (path := Path(env)).is_absolute():
        return path
    home = Path.home()
    if platform.system() == "Windows":
        return home / "AppData" / "Roaming"
    return home / ".config"


def parse_auth_inline(auth: str) -> AuthInfo | None:
    cookies: dict[str, str] = {}
    for part in auth.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        cookies[key.strip().lower()] = value.strip()

    sessdata = cookies.get("sessdata")
    if not sessdata:
        return None
    bili_jct = cookies.get("bili_jct")
    return AuthInfo(SESSDATA=sessdata, bili_jct=bili_jct or None)


def format_auth_inline(sessdata: str, bili_jct: str | None = None) -> str:
    if bili_jct:
        return f"SESSDATA={sessdata}; bili_jct={bili_jct}"
    return f"SESSDATA={sessdata}"


def default_auth_file() -> Path:
    return xdg_config_home() / "yutto" / "auth.toml"


def resolve_auth_file(args: Namespace) -> Path:
    if args.auth_file is not None:
        return args.auth_file
    return default_auth_file()


def validate_profile(profile: str):
    if not PROFILE_RE.match(profile):
        raise ValueError(f"auth profile 名称不合法：{profile}")


def load_auth_file(auth_file: Path) -> AuthFileModel | None:
    if not auth_file.exists():
        return None

    try:
        return AuthFileModel.model_validate(tomllib.loads(auth_file.read_text(encoding="utf-8")))
    except (ValidationError, ValueError):
        return None


def resolve_auth(args: Namespace) -> AuthInfo | None:
    if args.auth:
        parsed_auth = parse_auth_inline(args.auth)
        if parsed_auth is None:
            raise ValueError('auth 参数格式不正确哦，示例：--auth="SESSDATA=xxxxx; bili_jct=yyyyy"')
        return parsed_auth

    auth_file = resolve_auth_file(args)
    validate_profile(args.auth_profile)
    if not auth_file.exists():
        return None

    auth_file_model = load_auth_file(auth_file)
    if auth_file_model is None:
        raise ValueError(f"认证信息文件格式无效：{auth_file}")

    entry = auth_file_model.profiles.get(args.auth_profile)
    if entry is None or not entry.sessdata:
        return None
    return AuthInfo(SESSDATA=entry.sessdata, bili_jct=entry.bili_jct or None)


def load_auth(auth_file: Path, profile: str) -> AuthInfo | None:
    validate_profile(profile)
    auth_file_model = load_auth_file(auth_file)
    if auth_file_model is None:
        return None

    entry = auth_file_model.profiles.get(profile)
    if entry is None:
        return None
    if not entry.sessdata:
        return None
    return AuthInfo(SESSDATA=entry.sessdata, bili_jct=entry.bili_jct or None)


def save_auth(auth_file: Path, profile: str, sessdata: str, bili_jct: str | None):
    validate_profile(profile)

    profiles: dict[str, AuthProfileModel] = {}
    loaded = load_auth_file(auth_file)
    if loaded is not None:
        profiles = dict(loaded.profiles)

    original_entry = profiles.get(profile)
    entry_payload: dict[str, Any] = {}
    if original_entry is not None:
        entry_payload = original_entry.model_dump(exclude_none=True)

    entry_payload["sessdata"] = sessdata
    if bili_jct is not None:
        entry_payload["bili_jct"] = bili_jct
    else:
        entry_payload.pop("bili_jct", None)
    entry_payload["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    profiles[profile] = AuthProfileModel.model_validate(entry_payload)
    write_auth_file(auth_file, profiles)


def remove_auth(auth_file: Path, profile: str) -> bool:
    validate_profile(profile)
    loaded = load_auth_file(auth_file)
    if loaded is None:
        if auth_file.exists():
            raise ValueError(f"认证信息文件格式无效：{auth_file}")
        return False

    profiles = dict(loaded.profiles)
    if profile not in profiles:
        return False

    profiles.pop(profile)
    write_auth_file(auth_file, profiles)
    return True


def write_auth_file(auth_file: Path, profiles: dict[str, AuthProfileModel]) -> None:
    if not profiles:
        if auth_file.exists():
            auth_file.unlink()
        return

    auth_file.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for profile_name in sorted(profiles.keys()):
        profile_entry_dict = profiles[profile_name].model_dump(exclude_none=True)
        lines.append(f"[profiles.{profile_name}]")
        for key, value in profile_entry_dict.items():
            if isinstance(value, str):
                lines.append(f'{key} = "{escape_toml_basic_string(value)}"')
        lines.append("")

    auth_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    if os.name != "nt":
        auth_file.chmod(0o600)


def save_sessdata(auth_file: Path, profile: str, sessdata: str):
    save_auth(auth_file, profile, sessdata, None)


def escape_toml_basic_string(raw: str) -> str:
    return raw.replace("\\", "\\\\").replace('"', '\\"')
