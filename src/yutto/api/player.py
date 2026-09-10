from __future__ import annotations

from typing import TYPE_CHECKING, Any

from returns.result import Failure

from yutto.exceptions import NoAccessPermissionError
from yutto.utils.fetcher import Fetcher

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AvId, CId, EpisodeId


async def get_ugc_playurl(
    scope: ExecutionScope,
    avid: AvId,
    cid: CId,
    ai_translation_language: str | None = None,
) -> dict[str, Any]:
    play_api = (
        "https://api.bilibili.com/x/player/playurl?avid={aid}&bvid={bvid}&cid={cid}"
        "&qn=127&type=&otype=json&fnver=0&fnval=4048&fourk=1"
    )
    if ai_translation_language:
        play_api += f"&cur_language={ai_translation_language}"

    play_result = await Fetcher.fetch_json(scope, play_api.format(**avid.to_dict(), cid=cid))
    if isinstance(play_result, Failure):
        raise NoAccessPermissionError(f"无法获取该视频链接（{avid}, cid: {cid}）") from play_result.failure()

    response = play_result.unwrap()
    if response.get("data") is None:
        raise NoAccessPermissionError(f"无法获取该视频链接（{avid}, cid: {cid}），原因：{response.get('message')}")
    return response


async def get_bangumi_playurl(
    scope: ExecutionScope,
    avid: AvId,
    cid: CId,
) -> dict[str, Any]:
    play_api = (
        "https://api.bilibili.com/pgc/player/web/v2/playurl?avid={aid}&bvid={bvid}&cid={cid}"
        "&qn=127&fnver=0&fnval=4048&fourk=1&support_multi_audio=true&from_client=BROWSER"
    )
    play_result = await Fetcher.fetch_json(scope, play_api.format(**avid.to_dict(), cid=cid))
    if isinstance(play_result, Failure):
        raise NoAccessPermissionError(f"无法获取该视频链接（{avid}, cid: {cid}）") from play_result.failure()

    response = play_result.unwrap()
    result = response.get("result")
    if result is None or result.get("video_info") is None:
        raise NoAccessPermissionError(f"无法获取该视频链接（{avid}, cid: {cid}），原因：{response.get('message')}")
    return response


async def get_cheese_playurl(
    scope: ExecutionScope,
    avid: AvId,
    episode_id: EpisodeId,
    cid: CId,
) -> dict[str, Any]:
    play_api = (
        "https://api.bilibili.com/pugv/player/web/playurl?avid={aid}&cid={cid}"
        "&qn=80&fnver=0&fnval=16&fourk=1&ep_id={episode_id}&from_client=BROWSER&drm_tech_type=2"
    )
    play_result = await Fetcher.fetch_json(
        scope,
        play_api.format(**avid.to_dict(), cid=cid, episode_id=episode_id),
    )
    if isinstance(play_result, Failure):
        raise NoAccessPermissionError(f"无法获取该视频链接（{avid}, cid: {cid}）") from play_result.failure()

    response = play_result.unwrap()
    if response.get("data") is None:
        raise NoAccessPermissionError(f"无法获取该视频链接（{avid}, cid: {cid}），原因：{response.get('message')}")
    return response


def player_info_url(avid: AvId, cid: CId, *, wbi: bool) -> str:
    params = avid.to_dict()
    endpoint = "https://api.bilibili.com/x/player/wbi/v2" if wbi else "https://api.bilibili.com/x/player/v2"
    return f"{endpoint}?aid={params['aid']}&bvid={params['bvid']}&cid={cid}"


async def get_player_info(
    scope: ExecutionScope,
    avid: AvId,
    cid: CId,
    *,
    wbi: bool,
) -> dict[str, Any] | None:
    return (await Fetcher.fetch_json(scope, player_info_url(avid, cid, wbi=wbi))).value_or(None)


__all__ = [
    "get_bangumi_playurl",
    "get_cheese_playurl",
    "get_player_info",
    "get_ugc_playurl",
    "player_info_url",
]
