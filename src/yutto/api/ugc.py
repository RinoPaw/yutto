from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from returns.result import Failure

from yutto.api.account import encode_wbi, get_wbi_img
from yutto.api.common import fetch_payload
from yutto.core.operation import emit_download_report
from yutto.exceptions import NoAccessPermissionError, NotFoundError, NotLoginError
from yutto.types import AId, BvId, CId, FId, MId
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AvId, CollectionId, SeriesId

WATCH_LATER_API = "https://api.bilibili.com/x/v2/history/toview/web"


@dataclass(frozen=True, slots=True)
class UgcOwnerInfo:
    mid: MId | None
    name: str
    face: str


@dataclass(frozen=True, slots=True)
class UgcStaffInfo:
    mid: MId
    name: str
    role: str
    face: str


@dataclass(frozen=True, slots=True)
class UgcPageInfo:
    cid: CId
    title: str
    duration: int


@dataclass(frozen=True, slots=True)
class UgcVideoInfo:
    aid: AId
    bvid: BvId
    title: str
    description: str
    cover: str
    published_at: int
    duration: int
    category: str | None
    owner: UgcOwnerInfo | None
    staff: tuple[UgcStaffInfo, ...]
    pages: tuple[UgcPageInfo, ...]


@dataclass(frozen=True, slots=True)
class UgcVideoReference:
    bvid: BvId
    published_at: int | None


@dataclass(frozen=True, slots=True)
class UgcCollectionInfo:
    title: str
    videos: tuple[UgcVideoReference, ...]


@dataclass(frozen=True, slots=True)
class UgcFavouriteInfo:
    title: str
    description: str
    cover: str
    owner: UgcOwnerInfo | None


@dataclass(frozen=True, slots=True)
class UgcSeriesInfo:
    title: str
    owner_id: MId
    description: str


@dataclass(frozen=True, slots=True)
class UgcSpaceProfile:
    name: str
    description: str
    face: str


def _query(avid: AvId) -> str:
    return urlencode({key: value for key, value in avid.to_dict().items() if value})


def _dict_list(value: object, description: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise NoAccessPermissionError(f"无法解析{description}，原因：API 响应格式异常")
    return value


def _decode_optional_int(value: object, description: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise NoAccessPermissionError(f"无法解析{description}，原因：API 响应格式异常")
    try:
        return int(value)
    except ValueError as error:
        raise NoAccessPermissionError(f"无法解析{description}，原因：API 响应格式异常") from error


def _decode_ugc_owner(value: object) -> UgcOwnerInfo | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise NoAccessPermissionError("无法解析视频 UP 主信息，原因：API 响应格式异常")
    if not value:
        return None
    mid_value = value.get("mid")
    return UgcOwnerInfo(
        mid=MId(str(mid_value)) if mid_value is not None else None,
        name=str(value.get("name", "")),
        face=str(value.get("face", "")),
    )


def _decode_ugc_staff(value: object) -> tuple[UgcStaffInfo, ...]:
    staff: list[UgcStaffInfo] = []
    for item in _dict_list(value, "视频合作成员"):
        mid = item.get("mid")
        name = item.get("name")
        role = item.get("title")
        face = item.get("face")
        if mid is None or name is None or role is None or face is None:
            raise NoAccessPermissionError("无法解析视频合作成员，原因：API 响应缺少必要字段")
        staff.append(
            UgcStaffInfo(
                mid=MId(str(mid)),
                name=str(name),
                role=str(role),
                face=str(face),
            )
        )
    return tuple(staff)


def _decode_ugc_pages(value: object, *, video_title: str) -> tuple[UgcPageInfo, ...]:
    pages: list[UgcPageInfo] = []
    for item in _dict_list(value, "视频分 P"):
        cid = item.get("cid")
        if cid is None:
            raise NoAccessPermissionError("无法解析视频分 P，原因：API 响应缺少 cid")
        title = item.get("part")
        pages.append(
            UgcPageInfo(
                cid=CId(cid),
                title=str(title) if title is not None else video_title,
                duration=_decode_optional_int(item.get("duration"), "视频分 P 时长") or 0,
            )
        )
    return tuple(pages)


def _decode_ugc_video_info(data: dict[str, Any]) -> UgcVideoInfo:
    aid = data.get("aid")
    bvid = data.get("bvid")
    title = data.get("title")
    if aid is None or bvid is None or title is None:
        raise NoAccessPermissionError("无法解析视频信息，原因：API 响应缺少必要字段")

    video_title = str(title)
    category = data.get("tname")
    return UgcVideoInfo(
        aid=AId(aid),
        bvid=BvId(str(bvid)),
        title=video_title,
        description=str(data.get("desc", "")),
        cover=str(data.get("pic", "")),
        published_at=_decode_optional_int(data.get("pubdate"), "视频发布时间") or 0,
        duration=_decode_optional_int(data.get("duration"), "视频时长") or 0,
        category=category if isinstance(category, str) and category else None,
        owner=_decode_ugc_owner(data.get("owner")),
        staff=_decode_ugc_staff(data.get("staff")),
        pages=_decode_ugc_pages(data.get("pages"), video_title=video_title),
    )


def _decode_video_references(
    value: object,
    *,
    description: str,
    publication_field: str,
) -> tuple[UgcVideoReference, ...]:
    videos: list[UgcVideoReference] = []
    for item in _dict_list(value, description):
        bvid = item.get("bvid")
        if not bvid:
            continue
        videos.append(
            UgcVideoReference(
                bvid=BvId(str(bvid)),
                published_at=_decode_optional_int(item.get(publication_field), f"{description}发布时间"),
            )
        )
    return tuple(videos)


async def get_ugc_video_info(scope: ExecutionScope, avid: AvId) -> UgcVideoInfo:
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
    if not isinstance(data, dict):
        reason = response.get("message") or f"API 返回 code={response.get('code')}"
        raise NotFoundError(f"无法获取该视频 {avid} 信息，原因：{reason}")

    if data.get("forward"):
        forward_aid = AId(data["forward"])
        emit_download_report(f"视频 {avid} 撞车了哦！正在跳转到原视频 {forward_aid}～")
        return await get_ugc_video_info(scope, forward_aid)

    return _decode_ugc_video_info(data)


async def get_ugc_video_tags(scope: ExecutionScope, aid: AId) -> tuple[str, ...]:
    api = f"https://api.bilibili.com/x/tag/archive/tags?aid={aid.value}"
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, api))
    if response.get("code") != 0:
        raise NotFoundError(f"无法获取视频 {aid} 标签")
    raw_tags = response.get("data")
    if not isinstance(raw_tags, list):
        raise NotFoundError(f"无法获取视频 {aid} 标签，原因：API 响应格式异常")
    return tuple(str(tag["tag_name"]) for tag in raw_tags if isinstance(tag, dict) and tag.get("tag_name") is not None)


async def get_collection(
    scope: ExecutionScope,
    collection_id: CollectionId,
    owner_id: MId,
) -> UgcCollectionInfo:
    page_size = 30
    page_num = 1
    videos: list[UgcVideoReference] = []
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
            meta = payload.get("meta")
            if meta is not None and not isinstance(meta, dict):
                raise NoAccessPermissionError("无法解析视频合集，原因：API 响应格式异常")
            title = str((meta or {}).get("name", ""))

        page_archives = _dict_list(payload.get("archives"), "视频合集")
        videos.extend(
            _decode_video_references(
                page_archives,
                description="视频合集",
                publication_field="pubdate",
            )
        )

        page = payload.get("page")
        if page is not None and not isinstance(page, dict):
            raise NoAccessPermissionError("无法解析视频合集，原因：API 响应格式异常")
        total = (page or {}).get("total")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return UgcCollectionInfo(title=title, videos=tuple(videos))


async def get_favourite_info(scope: ExecutionScope, fid: FId) -> UgcFavouriteInfo:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/x/v3/fav/folder/info?media_id={fid}",
        "收藏夹",
        f"fid: {fid}",
        "data",
    )
    return UgcFavouriteInfo(
        title=str(payload.get("title", "")),
        description=str(payload.get("intro", "")),
        cover=str(payload.get("cover", "")),
        owner=_decode_ugc_owner(payload.get("upper")),
    )


async def get_favourite_medias(scope: ExecutionScope, fid: FId) -> tuple[UgcVideoReference, ...]:
    page_size = 20
    page_num = 1
    videos: list[UgcVideoReference] = []

    while True:
        payload = await fetch_payload(
            scope,
            f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={fid}&pn={page_num}&ps={page_size}&platform=web",
            "收藏夹",
            f"fid: {fid}",
            "data",
        )
        page_medias = _dict_list(payload.get("medias"), "收藏夹")
        videos.extend(
            _decode_video_references(
                page_medias,
                description="收藏夹",
                publication_field="pubtime",
            )
        )

        has_more = payload.get("has_more")
        if has_more is not None:
            if not has_more:
                break
        elif len(page_medias) < page_size:
            break
        page_num += 1

    return tuple(videos)


async def get_all_favourite_folders(scope: ExecutionScope, mid: MId) -> tuple[FId, ...]:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={mid}",
        "收藏夹列表",
        f"mid: {mid}",
        "data",
    )
    return tuple(
        FId(str(folder["id"]))
        for folder in _dict_list(payload.get("list"), "收藏夹列表")
        if folder.get("id") is not None
    )


async def get_series_info(scope: ExecutionScope, series_id: SeriesId) -> UgcSeriesInfo:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/x/series/series?series_id={series_id}",
        "视频系列",
        f"series_id: {series_id}",
        "data",
    )
    meta = payload.get("meta")
    if not isinstance(meta, dict) or meta.get("mid") is None:
        raise NoAccessPermissionError("无法解析视频系列，原因：API 响应缺少必要字段")
    return UgcSeriesInfo(
        title=str(meta.get("name", "")),
        owner_id=MId(str(meta["mid"])),
        description=str(meta.get("description", "")),
    )


async def get_series_archives(
    scope: ExecutionScope,
    series_id: SeriesId,
    mid: MId,
) -> tuple[UgcVideoReference, ...]:
    page_size = 30
    page_num = 1
    videos: list[UgcVideoReference] = []

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
        page_archives = _dict_list(payload.get("archives"), "视频系列")
        videos.extend(
            _decode_video_references(
                page_archives,
                description="视频系列",
                publication_field="pubdate",
            )
        )

        page = payload.get("page")
        if page is not None and not isinstance(page, dict):
            raise NoAccessPermissionError("无法解析视频系列，原因：API 响应格式异常")
        total = (page or {}).get("total")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return tuple(videos)


async def get_space_profile_and_archives(
    scope: ExecutionScope,
    mid: MId,
    *,
    stop_before_timestamp: int | None = None,
) -> tuple[UgcSpaceProfile, tuple[UgcVideoReference, ...]]:
    wbi_img = await get_wbi_img(scope)
    profile_payload = await fetch_payload(
        scope,
        "https://api.bilibili.com/x/space/wbi/acc/info",
        "UP 主",
        f"mid: {mid}",
        "data",
        params=encode_wbi({"mid": mid}, wbi_img),
    )
    profile = UgcSpaceProfile(
        name=str(profile_payload.get("name", "")),
        description=str(profile_payload.get("sign", "")),
        face=str(profile_payload.get("face", "")),
    )

    page_size = 30
    page_num = 1
    videos: list[UgcVideoReference] = []
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
        listing = payload.get("list")
        if listing is not None and not isinstance(listing, dict):
            raise NoAccessPermissionError("无法解析 UP 主空间，原因：API 响应格式异常")
        page_archives = _dict_list((listing or {}).get("vlist"), "UP 主空间")
        page_videos = _decode_video_references(
            page_archives,
            description="UP 主空间",
            publication_field="created",
        )
        videos.extend(page_videos)

        if stop_before_timestamp is not None and any(
            video.published_at is not None and video.published_at < stop_before_timestamp for video in page_videos
        ):
            break

        page = payload.get("page")
        if page is not None and not isinstance(page, dict):
            raise NoAccessPermissionError("无法解析 UP 主空间，原因：API 响应格式异常")
        total = (page or {}).get("count")
        if isinstance(total, int):
            if page_num * page_size >= total:
                break
        elif len(page_archives) < page_size:
            break
        page_num += 1

    return profile, tuple(videos)


async def get_watch_later_entries(scope: ExecutionScope) -> tuple[UgcVideoReference, ...]:
    response = unwrap_fetch_result(await Fetcher.fetch_json(scope, WATCH_LATER_API))
    if response.get("code") in {-101, -400}:
        raise NotLoginError("账号未登录，无法获取稍后再看列表哦~ Ծ‸Ծ")
    if response.get("code") == -404:
        raise NotFoundError("未找到稍后再看（watch_later）")
    payload = response.get("data")
    if not isinstance(payload, dict):
        raise NoAccessPermissionError(f"无法解析稍后再看（watch_later），原因：{response.get('message')}")
    return _decode_video_references(
        payload.get("list"),
        description="稍后再看",
        publication_field="pubdate",
    )


__all__ = [
    "UgcCollectionInfo",
    "UgcFavouriteInfo",
    "UgcOwnerInfo",
    "UgcPageInfo",
    "UgcSeriesInfo",
    "UgcSpaceProfile",
    "UgcStaffInfo",
    "UgcVideoInfo",
    "UgcVideoReference",
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
