from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from returns.result import Failure

from yutto.exceptions import ApiResponseError, NoAccessPermissionError, UnSupportedTypeError
from yutto.media.codec import audio_codec_map, video_codec_map
from yutto.types import AudioUrlMeta, VideoUrlMeta
from yutto.utils.fetcher import Fetcher

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AId, CId, EpisodeId


@dataclass(frozen=True, slots=True)
class TranslationLanguage:
    code: str
    title: str


@dataclass(frozen=True, slots=True)
class PlayUrlInfo:
    videos: tuple[VideoUrlMeta, ...]
    audios: tuple[AudioUrlMeta, ...]
    is_preview: bool = False
    is_drm: bool = False
    translation_languages: tuple[TranslationLanguage, ...] = ()


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    language: str
    url: str


@dataclass(frozen=True, slots=True)
class SubtitleInfo:
    tracks: tuple[SubtitleTrack, ...] | None
    invalid_languages: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class SubtitleLine:
    content: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class ChapterPoint:
    content: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ChapterInfo:
    points: tuple[ChapterPoint, ...] | None


def _video_streams(items: list[dict[str, Any]]) -> tuple[VideoUrlMeta, ...]:
    return tuple(
        VideoUrlMeta(
            url=item["base_url"],
            mirrors=tuple(item["backup_url"] or ()),
            codec=video_codec_map[item["codecid"]],
            width=item["width"],
            height=item["height"],
            quality=item["id"],
        )
        for item in items
    )


def _audio_streams(items: list[dict[str, Any]]) -> tuple[AudioUrlMeta, ...]:
    return tuple(
        AudioUrlMeta(
            url=item["base_url"],
            mirrors=tuple(item["backup_url"] or ()),
            codec=audio_codec_map[item["codecid"]],
            width=0,
            height=0,
            quality=item["id"],
        )
        for item in items
    )


def _dash_streams(
    dash: dict[str, Any],
    *,
    include_dolby: bool,
    include_flac: bool,
) -> tuple[tuple[VideoUrlMeta, ...], tuple[AudioUrlMeta, ...]]:
    videos = _video_streams(dash.get("video") or [])
    audios = list(_audio_streams(dash.get("audio") or []))

    if include_dolby:
        dolby = dash.get("dolby") or {}
        for item in dolby.get("audio") or []:
            audios.append(
                AudioUrlMeta(
                    url=item["base_url"],
                    mirrors=tuple(item["backup_url"] or ()),
                    codec="eac3",
                    width=0,
                    height=0,
                    quality=item["id"],
                )
            )

    if include_flac:
        flac = dash.get("flac") or {}
        item = flac.get("audio")
        if item:
            audios.append(
                AudioUrlMeta(
                    url=item["base_url"],
                    mirrors=tuple(item["backup_url"] or ()),
                    codec="flac",
                    width=0,
                    height=0,
                    quality=item["id"],
                )
            )

    return videos, tuple(audios)


def _translation_languages(data: dict[str, Any]) -> tuple[TranslationLanguage, ...]:
    language = data.get("language") or {}
    return tuple(
        TranslationLanguage(code=str(item["lang"]), title=str(item["title"]))
        for item in language.get("items") or []
        if item.get("lang") is not None and item.get("title") is not None
    )


def _decode_subtitle_info(response: dict[str, Any]) -> SubtitleInfo:
    data = response.get("data")
    if not isinstance(data, dict):
        return SubtitleInfo(tracks=None, message=str(response.get("message", "")))
    subtitle = data.get("subtitle")
    if not isinstance(subtitle, dict):
        return SubtitleInfo(tracks=None, message=str(response.get("message", "")))
    raw_subtitles = subtitle.get("subtitles")
    if not isinstance(raw_subtitles, list):
        return SubtitleInfo(tracks=None, message=str(response.get("message", "")))

    tracks: list[SubtitleTrack] = []
    invalid_languages: list[str] = []
    for item in raw_subtitles:
        if not isinstance(item, dict):
            raise ApiResponseError("无法解析字幕信息，原因：API 响应格式异常")
        language = str(item.get("lan_doc", "未知"))
        raw_url = item.get("subtitle_url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            invalid_languages.append(language)
            continue
        url = raw_url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https:{url}"
        tracks.append(SubtitleTrack(language=language, url=url))
    return SubtitleInfo(
        tracks=tuple(tracks),
        invalid_languages=tuple(invalid_languages),
        message=str(response.get("message", "")),
    )


def _decode_chapter_info(response: dict[str, Any]) -> ChapterInfo:
    data = response.get("data")
    if not isinstance(data, dict):
        return ChapterInfo(points=None)
    raw_chapters = data.get("view_points")
    if not isinstance(raw_chapters, list):
        return ChapterInfo(points=None)

    points: list[ChapterPoint] = []
    for item in raw_chapters:
        if not isinstance(item, dict):
            raise ApiResponseError("无法解析章节信息，原因：API 响应格式异常")
        content = item.get("content")
        start = item.get("from")
        end = item.get("to")
        if content is None or start is None or end is None:
            raise ApiResponseError("无法解析章节信息，原因：API 响应缺少必要字段")
        try:
            points.append(ChapterPoint(content=str(content), start=int(start), end=int(end)))
        except (TypeError, ValueError) as error:
            raise ApiResponseError("无法解析章节信息，原因：API 响应格式异常") from error
    return ChapterInfo(points=tuple(points))


async def get_ugc_playurl(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
    ai_translation_language: str | None = None,
) -> PlayUrlInfo:
    play_api = (
        f"https://api.bilibili.com/x/player/playurl?avid={aid}&cid={cid}"
        "&qn=127&type=&otype=json&fnver=0&fnval=4048&fourk=1"
    )
    if ai_translation_language:
        play_api += f"&cur_language={ai_translation_language}"

    play_result = await Fetcher.fetch_json(scope, play_api)
    if isinstance(play_result, Failure):
        raise NoAccessPermissionError(f"无法获取该视频链接（{aid}, cid: {cid}）") from play_result.failure()

    response = play_result.unwrap()
    data = response.get("data")
    if not isinstance(data, dict):
        raise NoAccessPermissionError(f"无法获取该视频链接（{aid}, cid: {cid}），原因：{response.get('message')}")
    dash = data.get("dash")
    if not isinstance(dash, dict):
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）尚不支持 DASH 格式")

    videos, audios = _dash_streams(dash, include_dolby=True, include_flac=True)
    return PlayUrlInfo(
        videos=videos,
        audios=audios,
        translation_languages=_translation_languages(data),
    )


async def get_bangumi_playurl(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
) -> PlayUrlInfo:
    play_api = (
        f"https://api.bilibili.com/pgc/player/web/v2/playurl?avid={aid}&cid={cid}"
        "&qn=127&fnver=0&fnval=4048&fourk=1&support_multi_audio=true&from_client=BROWSER"
    )
    play_result = await Fetcher.fetch_json(scope, play_api)
    if isinstance(play_result, Failure):
        raise NoAccessPermissionError(f"无法获取该视频链接（{aid}, cid: {cid}）") from play_result.failure()

    response = play_result.unwrap()
    result = response.get("result")
    video_info = result.get("video_info") if isinstance(result, dict) else None
    if not isinstance(video_info, dict):
        raise NoAccessPermissionError(f"无法获取该视频链接（{aid}, cid: {cid}），原因：{response.get('message')}")
    dash = video_info.get("dash")
    if not isinstance(dash, dict):
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）尚不支持 DASH 格式")

    videos, audios = _dash_streams(dash, include_dolby=True, include_flac=False)
    return PlayUrlInfo(
        videos=videos,
        audios=audios,
        is_preview=video_info.get("is_preview") == 1,
        is_drm=bool(video_info.get("is_drm")),
    )


async def get_cheese_playurl(
    scope: ExecutionScope,
    aid: AId,
    episode_id: EpisodeId,
    cid: CId,
) -> PlayUrlInfo:
    play_api = (
        f"https://api.bilibili.com/pugv/player/web/playurl?avid={aid}&cid={cid}"
        f"&qn=80&fnver=0&fnval=16&fourk=1&ep_id={episode_id}&from_client=BROWSER&drm_tech_type=2"
    )
    play_result = await Fetcher.fetch_json(scope, play_api)
    if isinstance(play_result, Failure):
        raise NoAccessPermissionError(f"无法获取该视频链接（{aid}, cid: {cid}）") from play_result.failure()

    response = play_result.unwrap()
    data = response.get("data")
    if not isinstance(data, dict):
        raise NoAccessPermissionError(f"无法获取该视频链接（{aid}, cid: {cid}），原因：{response.get('message')}")
    dash = data.get("dash")
    if not isinstance(dash, dict):
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）尚不支持 DASH 格式")

    videos, audios = _dash_streams(dash, include_dolby=False, include_flac=False)
    return PlayUrlInfo(
        videos=videos,
        audios=audios,
        is_preview=data.get("is_preview") == 1,
    )


def get_player_info_url(aid: AId, cid: CId, *, wbi: bool) -> str:
    endpoint = "https://api.bilibili.com/x/player/wbi/v2" if wbi else "https://api.bilibili.com/x/player/v2"
    return f"{endpoint}?aid={aid}&cid={cid}"


async def get_subtitle_info(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
    *,
    wbi: bool,
) -> SubtitleInfo | None:
    response = (await Fetcher.fetch_json(scope, get_player_info_url(aid, cid, wbi=wbi))).value_or(None)
    return _decode_subtitle_info(response) if response is not None else None


async def get_chapter_info(scope: ExecutionScope, url: str) -> ChapterInfo | None:
    response = (await Fetcher.fetch_json(scope, url)).value_or(None)
    return _decode_chapter_info(response) if response is not None else None


async def get_subtitle_lines(scope: ExecutionScope, url: str) -> tuple[SubtitleLine, ...] | None:
    response = (await Fetcher.fetch_json(scope, url)).value_or(None)
    if response is None or "body" not in response:
        return None
    body = response["body"]
    if not isinstance(body, list):
        raise ApiResponseError("无法解析字幕正文，原因：API 响应格式异常")

    lines: list[SubtitleLine] = []
    for item in body:
        if not isinstance(item, dict):
            raise ApiResponseError("无法解析字幕正文，原因：API 响应格式异常")
        content = item.get("content")
        start = item.get("from")
        end = item.get("to")
        if content is None or start is None or end is None:
            raise ApiResponseError("无法解析字幕正文，原因：API 响应缺少必要字段")
        try:
            lines.append(SubtitleLine(content=str(content), start=float(start), end=float(end)))
        except (TypeError, ValueError) as error:
            raise ApiResponseError("无法解析字幕正文，原因：API 响应格式异常") from error
    return tuple(lines)


__all__ = [
    "ChapterInfo",
    "ChapterPoint",
    "PlayUrlInfo",
    "SubtitleInfo",
    "SubtitleLine",
    "SubtitleTrack",
    "TranslationLanguage",
    "get_bangumi_playurl",
    "get_chapter_info",
    "get_cheese_playurl",
    "get_player_info_url",
    "get_subtitle_info",
    "get_subtitle_lines",
    "get_ugc_playurl",
]
