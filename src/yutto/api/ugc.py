from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from returns.result import Failure

from yutto.api.account import encode_wbi, get_wbi_img
from yutto.api.common import fetch_payload
from yutto.core.operation import emit_download_report
from yutto.exceptions import NoAccessPermissionError, NotFoundError, NotLoginError
from yutto.types import AId
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AvId, CollectionId, FId, MId, SeriesId

WATCH_LATER_API = "https://api.bilibili.com/x/v2/history/toview/web"


def _query(avid: AvId) -> str:
    return urlencode({key: value for key, value in avid.to_dict().items() if value})


async def get_ugc_video_info(scope: ExecutionScope, avid: AvId) -> tuple[AId, dict[str, Any]]:
    api = f"https://api.bilibili.com/x/web-interface/view?{_query(avid)}"
    result = await Fetcher.fetch_json(scope, api)
    if isinstance(result, Failure):
        raise NotFoundError(f"无法获取该视频 {avid} 信息") from result.failure()

    response = result.unwrap()
    data = response.get("data")
    if response["code"] == 62002:
        raise NotFoundError(f"无法下载该视频 {avid}，原因：{response['message']}")
    if response["code"] == 62012:
        raise NoAccessPermissionError(
            f"无法获取该视频 {avid} 信息，原因：{response['message']}（当前稿件UP主设置为仅自己可见）"
        )
    if response["code"] == -404:
        raise NotFoundError(f"哔咔！视频 {avid} 不见了诶")
    assert data is not None, "响应数据无 data 域"

    if data.get("forward"):
        forward_aid = AId(data["forward"])
        emit_download_report(f"视频 {avid} 撞车了哦！正在跳转到原视频 {forward_aid}～")
        return await get_ugc_video_info(scope, forward_aid)

    return AId(data["aid"]), data


async def get_ugc_video_tags(scope: ExecutionScope, avid: AvId) -> list[str]:
    api = f"https://api.bilibili.com/x/tag/archive/tags?{_query(avid)}"
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
    if response["code"] != 0:
        raise NotFoundError(f"无法获取视频 {avid} 标签")
    return [tag["tag_name"] for tag in response["data"]]


async def get_collection(
    scope: ExecutionScope,
    collection_id: CollectionId,
    owner_id: MId,
) -> tuple[str, list[dict[str, Any]]]:
    page_size = 30
    page_num = 1
    archives: list[dict[str, Any]] = []
    title = ""

    while True:
        payload = await fetch_payload(
            scope,
            (
                "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
                f"?mid={owner_id}&season_id={collection_id}&sort_reverse=false"
                f"&page_num={page_num}&page_size={page_size}"
            ),
            "视频合集",
            f"collection_id: {collection_id}",
            "data",
        )
        if page_num == 1:
            title = str(payload.get("meta", {}).get("name", ""))

        page_archives: list[dict[str, Any]] = payload.get("archives") or []
        archives.extend(item for item in page_archives if item.get("bvid"))

        total = payload.get("page", {}).get("total")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return title, archives


async def get_favourite_info(scope: ExecutionScope, fid: FId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/x/v3/fav/folder/info?media_id={fid}",
        "收藏夹",
        f"fid: {fid}",
        "data",
    )


async def get_favourite_medias(scope: ExecutionScope, fid: FId) -> list[dict[str, Any]]:
    page_size = 20
    page_num = 1
    medias: list[dict[str, Any]] = []

    while True:
        payload = await fetch_payload(
            scope,
            f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fid}&pn={page_num}&ps={page_size}&platform=web",
            "收藏夹",
            f"fid: {fid}",
            "data",
        )
        page_medias: list[dict[str, Any]] = payload.get("medias") or []
        medias.extend(item for item in page_medias if item.get("bvid"))

        has_more = payload.get("has_more")
        if has_more is not None:
            if not has_more:
                break
        elif len(page_medias) < page_size:
            break
        page_num += 1

    return medias


async def get_all_favourite_folders(scope: ExecutionScope, mid: MId) -> list[dict[str, Any]]:
    api = f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={mid}"
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
    data = response.get("data") or {}
    return list(data.get("list") or [])


async def get_series_info(scope: ExecutionScope, series_id: SeriesId) -> dict[str, Any]:
    return await fetch_payload(
        scope,
        f"https://api.bilibili.com/x/series/series?series_id={series_id}",
        "视频系列",
        f"series_id: {series_id}",
        "data",
    )


async def get_series_archives(scope: ExecutionScope, series_id: SeriesId, mid: MId) -> list[dict[str, Any]]:
    page_size = 30
    page_num = 1
    archives: list[dict[str, Any]] = []

    while True:
        payload = await fetch_payload(
            scope,
            (
                "https://api.bilibili.com/x/series/archives"
                f"?mid={mid}&series_id={series_id}&only_normal=true"
                f"&pn={page_num}&ps={page_size}"
            ),
            "视频系列",
            f"series_id: {series_id}",
            "data",
        )
        page_archives: list[dict[str, Any]] = payload.get("archives") or []
        archives.extend(item for item in page_archives if item.get("bvid"))

        total = payload.get("page", {}).get("total")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return archives


async def get_space_profile_and_archives(
    scope: ExecutionScope,
    mid: MId,
    *,
    stop_before_timestamp: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    wbi_img = await get_wbi_img(scope)
    profile = await fetch_payload(
        scope,
        "https://api.bilibili.com/x/space/wbi/acc/info",
        "UP 主",
        f"mid: {mid}",
        "data",
        params=encode_wbi({"mid": mid}, wbi_img),
    )

    page_size = 30
    page_num = 1
    archives: list[dict[str, Any]] = []
    while True:
        payload = await fetch_payload(
            scope,
            "https://api.bilibili.com/x/space/wbi/arc/search",
            "UP 主空间",
            f"mid: {mid}",
            "data",
            params=encode_wbi(
                {
                    "mid": mid,
                    "ps": page_size,
                    "tid": 0,
                    "pn": page_num,
                    "order": "pubdate",
                },
                wbi_img,
            ),
        )
        page_archives: list[dict[str, Any]] = payload.get("list", {}).get("vlist") or []
        archives.extend(item for item in page_archives if item.get("bvid"))

        if stop_before_timestamp is not None and any(
            item.get("created") is not None and int(item["created"]) < stop_before_timestamp for item in page_archives
        ):
            break

        total = payload.get("page", {}).get("count")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return profile, archives


async def get_watch_later_entries(scope: ExecutionScope) -> list[dict[str, Any]]:
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, WATCH_LATER_API))
    if response.get("code") in {-101, -400}:
        raise NotLoginError("账号未登录，无法获取稍后再看列表哦~ Ծ‸Ծ")
    if response.get("code") == -404:
        raise NotFoundError("未找到稍后再看（watch_later）")
    payload = response.get("data")
    if payload is None:
        raise NoAccessPermissionError(f"无法解析稍后再看（watch_later），原因：{response.get('message')}")
    return [item for item in payload.get("list", []) if item.get("bvid")]


__all__ = [
    "WATCH_LATER_API",
    "get_all_favourite_folders",
    "get_collection",
    "get_favourite_info",
    "get_favourite_medias",
    "get_series_archives",
    "get_series_info",
    "get_space_profile_and_archives",
    "get_ugc_video_info",
    "get_ugc_video_tags",
    "get_watch_later_entries",
]
