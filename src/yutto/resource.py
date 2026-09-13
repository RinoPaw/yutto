from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias

from biliass import get_danmaku_meta_size

from yutto.api.player import (
    get_bangumi_playurl as get_bangumi_playurl_response,
    get_cheese_playurl as get_cheese_playurl_response,
    get_player_info,
    get_ugc_playurl,
)
from yutto.auth import get_user_info
from yutto.core.operation import ReportColor, ReportLevel, emit_download_report
from yutto.exceptions import NoAccessPermissionError, UnSupportedTypeError
from yutto.media import BangumiEpisode, CheeseEpisode, MediaItem, UgcPage
from yutto.media.codec import audio_codec_map, video_codec_map
from yutto.types import AudioUrlMeta, VideoUrlMeta
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.functional import data_has_chained_keys

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.core.request import DownloadRequest
    from yutto.types import AId, CId, EpisodeId
    from yutto.utils.danmaku import DanmakuSaveType, DanmakuSourceType

SubtitleResource: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceManifest:
    """Resolved resource locations for one MediaItem; contains no fetched resource bodies."""

    videos: tuple[VideoUrlMeta, ...] = ()
    audios: tuple[AudioUrlMeta, ...] = ()
    subtitles: tuple[SubtitleResource, ...] = ()
    danmaku_source_type: DanmakuSourceType | None = None
    danmaku_save_type: DanmakuSaveType | None = None
    danmaku_urls: tuple[str, ...] = ()
    cover_url: str | None = None
    chapter_info_url: str | None = None


def _video_streams(items: list[dict[str, Any]]) -> list[VideoUrlMeta]:
    return [
        VideoUrlMeta(
            url=item["base_url"],
            mirrors=item["backup_url"] if item["backup_url"] is not None else [],
            codec=video_codec_map[item["codecid"]],
            width=item["width"],
            height=item["height"],
            quality=item["id"],
        )
        for item in items
    ]


def _audio_streams(items: list[dict[str, Any]]) -> list[AudioUrlMeta]:
    return [
        AudioUrlMeta(
            url=item["base_url"],
            mirrors=item["backup_url"] if item["backup_url"] is not None else [],
            codec=audio_codec_map[item["codecid"]],
            width=0,
            height=0,
            quality=item["id"],
        )
        for item in items
    ]


def _append_dolby_audio(audios: list[AudioUrlMeta], dash: dict[str, Any]) -> None:
    dolby = dash.get("dolby")
    if not dolby or not dolby.get("audio"):
        return
    audios.extend(
        AudioUrlMeta(
            url=item["base_url"],
            mirrors=item["backup_url"] if item["backup_url"] is not None else [],
            codec="eac3",
            width=0,
            height=0,
            quality=item["id"],
        )
        for item in dolby["audio"]
    )


def _append_flac_audio(audios: list[AudioUrlMeta], dash: dict[str, Any]) -> None:
    flac = dash.get("flac")
    if not flac or not flac.get("audio"):
        return
    item = flac["audio"]
    audios.append(
        AudioUrlMeta(
            url=item["base_url"],
            mirrors=item["backup_url"] if item["backup_url"] is not None else [],
            codec="flac",
            width=0,
            height=0,
            quality=item["id"],
        )
    )


def show_ai_translation_language(resp_json: dict[str, Any], ai_translation_language: str | None) -> None:
    if not data_has_chained_keys(resp_json, ["data", "language", "items"]):
        if ai_translation_language:
            emit_download_report(
                f"该视频未启用 AI 原声翻译功能, 无法获得 {ai_translation_language} 语言翻译哦～",
                ReportLevel.WARNING,
            )
        return
    items = resp_json["data"]["language"]["items"]
    if not items:
        if ai_translation_language:
            emit_download_report(
                f"该视频未启用 AI 原声翻译功能, 无法获得 {ai_translation_language} 语言翻译哦～",
                ReportLevel.WARNING,
            )
        return

    current_lang_id = -1
    emit_download_report("该视频已启用的 AI 原声翻译语言列表：")
    for index, lang_info in enumerate(items):
        if lang_info["lang"] == ai_translation_language:
            current_lang_id = index
        log = "{}{:2} {} (code: {})".format(
            "*" if index == current_lang_id else " ",
            index,
            lang_info["title"],
            lang_info["lang"],
        )
        if index == current_lang_id:
            emit_download_report(log, color=ReportColor.GREEN)
        else:
            emit_download_report(log)

    if current_lang_id != -1:
        return
    if ai_translation_language:
        emit_download_report(
            f"该视频未为语言 {ai_translation_language} 支持 AI 原声翻译功能哦～",
            ReportLevel.WARNING,
        )
        return
    emit_download_report("若想启用 AI 原声翻译功能，可以使用 `--ai-translation-language=<code>` 参数指定目标语言喔～")


async def get_ugc_video_playurl(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
    ai_translation_language: str | None = None,
) -> tuple[list[VideoUrlMeta], list[AudioUrlMeta]]:
    resp_json = await get_ugc_playurl(scope, aid, cid, ai_translation_language)
    dash = resp_json["data"].get("dash")
    if dash is None:
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）尚不支持 DASH 格式")

    videos = _video_streams(dash.get("video") or [])
    audios = _audio_streams(dash.get("audio") or [])
    _append_dolby_audio(audios, dash)
    _append_flac_audio(audios, dash)
    show_ai_translation_language(resp_json, ai_translation_language)
    return videos, audios


async def get_bangumi_playurl(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
) -> tuple[list[VideoUrlMeta], list[AudioUrlMeta]]:
    resp_json = await get_bangumi_playurl_response(scope, aid, cid)
    video_info = resp_json["result"]["video_info"]
    if video_info.get("is_preview") == 1:
        emit_download_report(
            f"视频（{aid}, cid: {cid}）是预览视频（疑似未登录或非大会员用户）",
            ReportLevel.WARNING,
        )
    dash = video_info.get("dash")
    if dash is None:
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）尚不支持 DASH 格式")

    videos = _video_streams(dash.get("video") or [])
    audios = _audio_streams(dash.get("audio") or [])
    _append_dolby_audio(audios, dash)
    return videos, audios


async def get_cheese_playurl(
    scope: ExecutionScope,
    aid: AId,
    episode_id: EpisodeId,
    cid: CId,
) -> tuple[list[VideoUrlMeta], list[AudioUrlMeta]]:
    resp_json = await get_cheese_playurl_response(scope, aid, episode_id, cid)
    data = resp_json["data"]
    if data.get("is_preview") == 1:
        emit_download_report(
            f"视频（{aid}, cid: {cid}）是预览视频（疑似未登录或非大会员用户）",
            ReportLevel.WARNING,
        )
    dash = data.get("dash")
    if dash is None:
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）尚不支持 DASH 格式")
    return _video_streams(dash.get("video") or []), _audio_streams(dash.get("audio") or [])


async def _resolve_subtitles(
    scope: ExecutionScope,
    item: MediaItem,
    aid: AId,
    cid: CId,
) -> list[SubtitleResource]:
    resp_json = await get_player_info(scope, aid, cid, wbi=not isinstance(item, CheeseEpisode))
    if resp_json is None:
        return []
    if not data_has_chained_keys(resp_json, ["data", "subtitle", "subtitles"]):
        if not isinstance(item, UgcPage):
            emit_download_report(
                f"无法获取该视频的字幕（{aid}, cid: {cid}），原因：{resp_json.get('message')}",
                ReportLevel.WARNING,
            )
        return []

    subtitles: list[SubtitleResource] = []
    for sub_info in resp_json["data"]["subtitle"]["subtitles"]:
        subtitle_url = sub_info["subtitle_url"]
        if subtitle_url is None or not subtitle_url.strip():
            emit_download_report(
                f"跳过无效的字幕URL（{aid}, cid: {cid}），语言：{sub_info.get('lan_doc', '未知')}",
                ReportLevel.WARNING,
            )
            continue
        if not subtitle_url.startswith(("http://", "https://")):
            subtitle_url = f"https:{subtitle_url}"
        subtitles.append((sub_info["lan_doc"], subtitle_url))
    return subtitles


async def _resolve_danmaku(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
    save_type: DanmakuSaveType,
) -> tuple[DanmakuSourceType, list[str]]:
    source_type: DanmakuSourceType = (
        "xml" if save_type == "xml" or not (await get_user_info(scope))["is_login"] else "protobuf"
    )
    if source_type == "xml":
        return source_type, [f"http://comment.bilibili.com/{cid}.xml"]

    meta = unwrap_fetch_result(
        await Fetcher.fetch_bin(
            scope,
            f"https://api.bilibili.com/x/v2/dm/web/view?type=1&oid={cid}&pid={aid.value}",
        )
    )
    if meta is None:
        raise NoAccessPermissionError(f"无法获取该视频弹幕元数据（{aid}, cid: {cid}）")
    size = get_danmaku_meta_size(meta)
    return source_type, [
        f"http://api.bilibili.com/x/v2/dm/web/seg.so?type=1&oid={cid}&segment_index={segment_id}"
        for segment_id in range(1, size + 1)
    ]


async def resolve_resource_manifest(
    scope: ExecutionScope,
    item: MediaItem,
    request: DownloadRequest,
) -> ResourceManifest:
    """Resolve resource locations for one MediaItem without downloading resource bodies."""

    resources = request.resources
    videos: list[VideoUrlMeta] = []
    audios: list[AudioUrlMeta] = []
    subtitles: list[SubtitleResource] = []
    chapter_info_url: str | None = None

    if isinstance(item, UgcPage):
        aid = item.aid
        if resources.video or resources.audio:
            videos, audios = await get_ugc_video_playurl(
                scope,
                aid,
                item.cid,
                resources.ai_translation_language,
            )
        if resources.chapter_info:
            chapter_info_url = f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={item.cid}"
    elif isinstance(item, BangumiEpisode):
        aid = item.aid
        if resources.video or resources.audio:
            videos, audios = await get_bangumi_playurl(scope, aid, item.cid)
    elif isinstance(item, CheeseEpisode):
        aid = item.aid
        if resources.video or resources.audio:
            videos, audios = await get_cheese_playurl(scope, aid, item.episode_id, item.cid)
    else:
        raise TypeError(f"unsupported media item: {type(item).__name__}")

    if resources.subtitle:
        subtitles = await _resolve_subtitles(scope, item, aid, item.cid)
    if not resources.video:
        videos = []
    if not resources.audio:
        audios = []

    danmaku_source_type: DanmakuSourceType | None = None
    danmaku_urls: list[str] = []
    if resources.danmaku:
        danmaku_source_type, danmaku_urls = await _resolve_danmaku(
            scope,
            aid,
            item.cid,
            request.danmaku.format,
        )

    return ResourceManifest(
        videos=tuple(videos),
        audios=tuple(audios),
        subtitles=tuple(subtitles),
        danmaku_source_type=danmaku_source_type,
        danmaku_save_type=request.danmaku.format if danmaku_urls else None,
        danmaku_urls=tuple(danmaku_urls),
        cover_url=item.metadata.thumb if resources.cover and item.metadata.thumb else None,
        chapter_info_url=chapter_info_url,
    )
