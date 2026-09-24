from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from yutto.api.common import fetch_payload
from yutto.exceptions import NotFoundError
from yutto.types import AId, BvId, CId, EpisodeId, MId, SeasonId

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import MediaId


@dataclass(frozen=True, slots=True)
class BangumiOwnerInfo:
    mid: MId | None
    name: str
    avatar: str


@dataclass(frozen=True, slots=True)
class BangumiEpisodeInfo:
    episode_id: EpisodeId
    aid: AId
    cid: CId
    title: str
    show_title: str
    cover: str
    published_at: int | None
    duration: int
    is_preview: bool


@dataclass(frozen=True, slots=True)
class BangumiSeasonInfo:
    season_id: SeasonId
    title: str
    description: str
    owner: BangumiOwnerInfo | None
    genres: tuple[str, ...]
    episodes: tuple[BangumiEpisodeInfo, ...]
    main_episode_count: int


@dataclass(frozen=True, slots=True)
class CheeseEpisodeInfo:
    episode_id: EpisodeId
    aid: AId
    cid: CId
    title: str
    cover: str
    published_at: int | None
    duration: int


@dataclass(frozen=True, slots=True)
class CheeseSeasonInfo:
    season_id: SeasonId | None
    title: str
    episodes: tuple[CheeseEpisodeInfo, ...]


def _dict_list(value: object, description: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise NotFoundError(f"无法解析{description}，原因：API 响应格式异常")
    return value


def _optional_int(value: object, description: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise NotFoundError(f"无法解析{description}，原因：API 响应格式异常")
    try:
        return int(value)
    except ValueError as error:
        raise NotFoundError(f"无法解析{description}，原因：API 响应格式异常") from error


def _decode_bangumi_episode(item: dict[str, Any]) -> BangumiEpisodeInfo:
    episode_id = item.get("id")
    cid = item.get("cid")
    short_title = item.get("title")
    if episode_id is None or cid is None or short_title is None:
        raise NotFoundError("无法解析番剧剧集，原因：API 响应缺少必要字段")

    aid_value = item.get("aid")
    bvid_value = item.get("bvid")
    if aid_value is not None:
        aid = AId(aid_value)
    elif bvid_value is not None:
        aid = BvId(str(bvid_value)).as_aid()
    else:
        raise NotFoundError("无法解析番剧剧集，原因：API 响应缺少 aid/bvid")

    long_title = str(item.get("long_title", ""))
    title = f"{short_title} {long_title}" if long_title else str(short_title)
    show_title = str(item.get("share_copy", title))
    duration_ms = _optional_int(item.get("duration"), "番剧剧集时长") or 0
    return BangumiEpisodeInfo(
        episode_id=EpisodeId(str(episode_id)),
        aid=aid,
        cid=CId(cid),
        title=title,
        show_title=show_title,
        cover=str(item.get("cover", "")),
        published_at=_optional_int(item.get("pub_time"), "番剧剧集发布时间"),
        duration=duration_ms // 1000,
        is_preview=item.get("badge") == "预告",
    )


def _decode_bangumi_season(payload: dict[str, Any], id: SeasonId | EpisodeId) -> BangumiSeasonInfo:
    season_id = payload.get("season_id")
    if season_id is None:
        raise NotFoundError(f"无法解析该番剧（{id}），原因：API 响应缺少 season_id")

    main_items = _dict_list(payload.get("episodes"), "番剧剧集列表")
    episodes = [_decode_bangumi_episode(item) for item in main_items]
    main_episode_count = len(episodes)

    for section in _dict_list(payload.get("section"), "番剧分区"):
        if section.get("type") == 5:
            continue
        episodes.extend(
            _decode_bangumi_episode(item)
            for item in _dict_list(section.get("episodes"), "番剧附加剧集列表")
        )

    up_info = payload.get("up_info")
    if up_info is not None and not isinstance(up_info, dict):
        raise NotFoundError(f"无法解析该番剧（{id}），原因：API 响应格式异常")
    owner: BangumiOwnerInfo | None = None
    if up_info:
        mid_value = up_info.get("mid")
        owner = BangumiOwnerInfo(
            mid=MId(str(mid_value)) if mid_value is not None else None,
            name=str(up_info.get("uname", "")),
            avatar=str(up_info.get("avatar", "")),
        )

    styles = payload.get("styles") or []
    if not isinstance(styles, list):
        raise NotFoundError(f"无法解析该番剧（{id}），原因：API 响应格式异常")
    return BangumiSeasonInfo(
        season_id=SeasonId(str(season_id)),
        title=str(payload.get("title", "")),
        description=str(payload.get("evaluate", "")),
        owner=owner,
        genres=tuple(str(style) for style in styles),
        episodes=tuple(episodes),
        main_episode_count=main_episode_count,
    )


def _decode_cheese_episode(item: dict[str, Any]) -> CheeseEpisodeInfo:
    episode_id = item.get("id")
    aid = item.get("aid")
    cid = item.get("cid")
    title = item.get("title")
    if episode_id is None or aid is None or cid is None or title is None:
        raise NotFoundError("无法解析课程剧集，原因：API 响应缺少必要字段")
    return CheeseEpisodeInfo(
        episode_id=EpisodeId(str(episode_id)),
        aid=AId(aid),
        cid=CId(cid),
        title=str(title),
        cover=str(item.get("cover", "")),
        published_at=_optional_int(item.get("release_date"), "课程剧集发布时间"),
        duration=_optional_int(item.get("duration"), "课程剧集时长") or 0,
    )


def _decode_cheese_season(payload: dict[str, Any]) -> CheeseSeasonInfo:
    season_id = payload.get("season_id")
    return CheeseSeasonInfo(
        season_id=SeasonId(str(season_id)) if season_id is not None else None,
        title=str(payload.get("title", "")),
        episodes=tuple(
            _decode_cheese_episode(item)
            for item in _dict_list(payload.get("episodes"), "课程剧集列表")
        ),
    )


async def get_bangumi_season(scope: ExecutionScope, id: SeasonId | EpisodeId) -> BangumiSeasonInfo:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/pgc/view/web/season?{urlencode(id.to_dict())}",
        "该番剧",
        str(id),
        "result",
    )
    if not isinstance(payload.get("episodes"), list):
        raise NotFoundError(f"无法解析该番剧（{id}），原因：API 响应缺少剧集列表")
    return _decode_bangumi_season(payload, id)


get_bangumi_season_by_episode = get_bangumi_season


async def get_season_id_by_media(scope: ExecutionScope, media_id: MediaId) -> SeasonId:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/pgc/review/user?{urlencode(media_id.to_dict())}",
        "该番剧",
        str(media_id),
        "result",
    )
    media = payload.get("media")
    season_id = media.get("season_id") if isinstance(media, dict) else None
    if season_id is None:
        raise NotFoundError(f"无法解析该番剧（{media_id}），原因：API 响应缺少 season_id")
    return SeasonId(str(season_id))


async def get_cheese_season(scope: ExecutionScope, id: SeasonId | EpisodeId) -> CheeseSeasonInfo:
    payload = await fetch_payload(
        scope,
        f"https://api.bilibili.com/pugv/view/web/season?{urlencode(id.to_dict())}",
        "该课程",
        str(id),
        "data",
    )
    if not isinstance(payload.get("episodes"), list):
        raise NotFoundError(f"无法解析该课程（{id}），原因：API 响应缺少剧集列表")
    return _decode_cheese_season(payload)


get_cheese_season_by_episode = get_cheese_season


__all__ = [
    "BangumiEpisodeInfo",
    "BangumiOwnerInfo",
    "BangumiSeasonInfo",
    "CheeseEpisodeInfo",
    "CheeseSeasonInfo",
    "get_bangumi_season",
    "get_bangumi_season_by_episode",
    "get_cheese_season",
    "get_cheese_season_by_episode",
    "get_season_id_by_media",
]
