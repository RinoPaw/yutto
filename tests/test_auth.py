from __future__ import annotations

import asyncio
from argparse import Namespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from returns.result import Success

from yutto.auth import (
    format_auth_inline,
    get_user_info,
    get_wbi_img,
    load_auth,
    parse_auth_inline,
    parse_user_info,
    remove_auth,
    resolve_auth,
    save_auth,
    user_info_matches,
    validate_user_info,
)
from yutto.core.execution import ExecutionScope
from yutto.types import UserInfo
from yutto.utils.fetcher import Fetcher
from yutto.utils.functional import as_sync

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_auth_inline_handles_case_and_spaces():
    assert parse_auth_inline("  SESSDATA = foo ; BILI_JCT = bar  ") == {"SESSDATA": "foo", "bili_jct": "bar"}


def test_parse_auth_inline_requires_sessdata():
    assert parse_auth_inline("foo=bar; bili_jct=baz") is None


def test_format_auth_inline_omits_empty_bili_jct():
    assert format_auth_inline("foo") == "SESSDATA=foo"


def test_resolve_auth_prefers_inline_auth(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"
    save_auth(auth_file, "default", "from-file", "csrf")

    args = Namespace(
        auth="SESSDATA=from-inline; bili_jct=inline-csrf",
        auth_file=auth_file,
        auth_profile="default",
    )

    assert resolve_auth(args) == {"SESSDATA": "from-inline", "bili_jct": "inline-csrf"}


def test_resolve_auth_rejects_invalid_auth_file(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"
    auth_file.write_text("[profiles.default]\nsessdata = 123\n", encoding="utf-8")

    args = Namespace(
        auth="",
        auth_file=auth_file,
        auth_profile="default",
    )

    with pytest.raises(ValueError, match="认证信息文件格式无效"):
        resolve_auth(args)


def test_save_and_load_auth_round_trip(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    save_auth(auth_file, "default", "sessdata-value", "csrf-value")

    assert load_auth(auth_file, "default") == {"SESSDATA": "sessdata-value", "bili_jct": "csrf-value"}


def test_save_auth_clears_stale_bili_jct(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    save_auth(auth_file, "default", "old-sessdata", "old-csrf")
    save_auth(auth_file, "default", "new-sessdata", None)

    assert load_auth(auth_file, "default") == {"SESSDATA": "new-sessdata", "bili_jct": None}
    assert "bili_jct" not in auth_file.read_text(encoding="utf-8")


def test_load_auth_returns_none_for_invalid_file(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"
    auth_file.write_text("[profiles.default]\nsessdata = 123\n", encoding="utf-8")

    assert load_auth(auth_file, "default") is None


def test_load_auth_rejects_invalid_profile(tmp_path: Path):
    with pytest.raises(ValueError, match="auth profile 名称不合法"):
        load_auth(tmp_path / "auth.toml", "bad profile")


def test_remove_auth_removes_target_profile_only(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    save_auth(auth_file, "default", "sessdata-default", "csrf-default")
    save_auth(auth_file, "work", "sessdata-work", "csrf-work")

    assert remove_auth(auth_file, "default")
    assert load_auth(auth_file, "default") is None
    assert load_auth(auth_file, "work") == {"SESSDATA": "sessdata-work", "bili_jct": "csrf-work"}


def test_remove_auth_deletes_empty_auth_file(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    save_auth(auth_file, "default", "sessdata-value", "csrf-value")

    assert remove_auth(auth_file, "default")
    assert not auth_file.exists()


def test_remove_auth_returns_false_when_profile_missing(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"

    assert not remove_auth(auth_file, "default")


def test_remove_auth_rejects_invalid_existing_auth_file(tmp_path: Path):
    auth_file = tmp_path / "auth.toml"
    auth_file.write_text("[profiles.default]\nsessdata = 123\n", encoding="utf-8")

    with pytest.raises(ValueError, match="认证信息文件格式无效"):
        remove_auth(auth_file, "default")


def test_parse_user_info():
    assert parse_user_info({"data": {"vipStatus": 1, "isLogin": True}}) == {
        "vip_status": True,
        "is_login": True,
    }


def test_user_info_matches():
    assert user_info_matches(
        {"vip_status": True, "is_login": True},
        {"vip_status": True, "is_login": False},
    )
    assert not user_info_matches(
        {"vip_status": False, "is_login": True},
        {"vip_status": True, "is_login": False},
    )


@pytest.mark.processor
@as_sync
async def test_user_info_cache_is_scoped_to_execution_scope(monkeypatch: pytest.MonkeyPatch):
    responses = iter(
        [
            {"data": {"vipStatus": 1, "isLogin": True}},
            {"data": {"vipStatus": 0, "isLogin": False}},
        ]
    )
    calls = 0

    async def fake_fetch_json(scope: object, url: str):
        nonlocal calls
        calls += 1
        return Success(next(responses))

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)
    first_scope = ExecutionScope(cast("Any", object()))
    second_scope = ExecutionScope(cast("Any", object()))

    assert await get_user_info(first_scope) == {"vip_status": True, "is_login": True}
    assert await get_user_info(first_scope) == {"vip_status": True, "is_login": True}
    assert await get_user_info(second_scope) == {"vip_status": False, "is_login": False}
    assert calls == 2


@pytest.mark.processor
@as_sync
async def test_validate_user_info_reuses_execution_scope_session_and_cache(monkeypatch: pytest.MonkeyPatch):
    session = cast("Any", object())
    scope = ExecutionScope(session)
    sessions: list[Any] = []

    async def fake_fetch_json(active_scope: ExecutionScope, url: str):
        sessions.append(active_scope.session)
        return Success({"data": {"vipStatus": 1, "isLogin": True}})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)

    requirements = UserInfo(vip_status=True, is_login=True)
    assert await validate_user_info(scope, requirements)
    assert await validate_user_info(scope, requirements)
    assert sessions == [session]


@pytest.mark.processor
@as_sync
async def test_concurrent_user_info_reads_share_one_fetch(monkeypatch: pytest.MonkeyPatch):
    calls = 0

    async def fake_fetch_json(scope: ExecutionScope, url: str):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return Success({"data": {"vipStatus": 1, "isLogin": True}})

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)
    scope = ExecutionScope(cast("Any", object()))

    results = await asyncio.gather(get_user_info(scope), get_user_info(scope))

    assert results == [
        {"vip_status": True, "is_login": True},
        {"vip_status": True, "is_login": True},
    ]
    assert calls == 1


@pytest.mark.processor
@as_sync
async def test_wbi_cache_is_scoped_to_execution_scope(monkeypatch: pytest.MonkeyPatch):
    responses = iter(
        [
            {
                "data": {
                    "wbi_img": {
                        "img_url": "https://example.com/first-img.png",
                        "sub_url": "https://example.com/first-sub.png",
                    }
                }
            },
            {
                "data": {
                    "wbi_img": {
                        "img_url": "https://example.com/second-img.png",
                        "sub_url": "https://example.com/second-sub.png",
                    }
                }
            },
        ]
    )
    calls = 0

    async def fake_fetch_json(scope: ExecutionScope, url: str):
        nonlocal calls
        calls += 1
        return Success(next(responses))

    monkeypatch.setattr(Fetcher, "fetch_json", fake_fetch_json)
    first_scope = ExecutionScope(cast("Any", object()))
    second_scope = ExecutionScope(cast("Any", object()))

    assert await get_wbi_img(first_scope) == {"img_key": "first-img", "sub_key": "first-sub"}
    assert await get_wbi_img(first_scope) == {"img_key": "first-img", "sub_key": "first-sub"}
    assert await get_wbi_img(second_scope) == {"img_key": "second-img", "sub_key": "second-sub"}
    assert calls == 2
