from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias, cast

from yutto.api.danmaku import get_protobuf_danmaku_urls, get_xml_danmaku_url
from yutto.api.player import (
    TranslationLanguage,
    get_bangumi_playurl,
    get_cheese_playurl,
    get_player_info,
    get_player_info_url,
    get_ugc_playurl,
)
from yutto.auth import get_user_info
from yutto.core.operation import ReportColor, ReportLevel, emit_download_report
from yutto.exceptions import UnSupportedTypeError
from yutto.media import BangumiEpisode, CheeseEpisode, MediaItem, UgcPage
from yutto.types import AudioUrlMeta, VideoUrlMeta
from yutto.utils.functional import data_has_chained_keys

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.scope import Scope
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


def wants_video(scope: Scope) -> bool:
    return bool(scope.resource.video)


def wants_audio(scope: Scope) -> bool:
    return bool(scope.resource.audio)


def wants_danmaku(scope: Scope) -> bool:
    return bool(scope.resource.danmaku)


def wants_subtitle(scope: Scope) -> bool:
    return bool(scope.resource.subtitle)


def wants_metadata(scope: Scope) -> bool:
    return bool(scope.resource.metadata)


def wants_cover(scope: Scope) -> bool:
    return bool(scope.resource.cover)


def wants_chapter_info(scope: Scope) -> bool:
    return bool(scope.resource.chapter_info)


def should_save_cover(scope: Scope) -> bool:
    cover = wants_cover(scope)
    save_cover = bool(scope.resource.save_cover)
    if save_cover and not cover:
        raise ValueError("save_cover requires cover")
    if cover and not any(
        (
            wants_video(scope),
            wants_audio(scope),
            wants_danmaku(scope),
            wants_subtitle(scope),
            wants_metadata(scope),
            wants_chapter_info(scope),
        )
    ):
        return True
    return save_cover


def resolve_danmaku_format(scope: Scope) -> DanmakuSaveType:
    value = scope.danmaku.format
    if value not in {"xml", "ass", "protobuf"}:
        raise ValueError(f"unsupported danmaku format: {value}")
    return cast("DanmakuSaveType", value)


def show_ai_translation_language(
    languages: tuple[TranslationLanguage, ...],
    ai_translation_language: str | None,
) -> None:
    if not languages:
        if ai_translation_language:
            emit_download_report(
                f"该视频未启用 AI 原声翻译功能, 无法获得 {ai_translation_language} 语言翻译哦～",
                ReportLevel.WARNING,
            )
        return

    current_lang_id = -1
    emit_download_report("该视频已启用的 AI 原声翻译语言列表：")
    for index, language in enumerate(languages):
        if language.code == ai_translation_language:
            current_lang_id = index
        log = "{}{:2} {} (code: {})".format(
            "*" if index == current_lang_id else " ",
            index,
            language.title,
            language.code,
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
) -> tuple[tuple[VideoUrlMeta, ...], tuple[AudioUrlMeta, ...]]:
    play_url = await get_ugc_playurl(scope, aid, cid, ai_translation_language)
    show_ai_translation_language(play_url.translation_languages, ai_translation_language)
    return play_url.videos, play_url.audios


async def get_bangumi_video_playurl(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
) -> tuple[tuple[VideoUrlMeta, ...], tuple[AudioUrlMeta, ...]]:
    play_url = await get_bangumi_playurl(scope, aid, cid)
    if play_url.is_drm:
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）使用 DRM 保护，当前暂不支持处理 DRM 媒体")
    if play_url.is_preview:
        emit_download_report(
            f"视频（{aid}, cid: {cid}）是预览视频（疑似未登录或非大会员用户）",
            ReportLevel.WARNING,
        )
    return play_url.videos, play_url.audios


async def get_cheese_video_playurl(
    scope: ExecutionScope,
    aid: AId,
    episode_id: EpisodeId,
    cid: CId,
) -> tuple[tuple[VideoUrlMeta, ...], tuple[AudioUrlMeta, ...]]:
    play_url = await get_cheese_playurl(scope, aid, episode_id, cid)
    if play_url.is_preview:
        emit_download_report(
            f"视频（{aid}, cid: {cid}）是预览视频（疑似未登录或非大会员用户）",
            ReportLevel.WARNING,
        )
    return play_url.videos, play_url.audios


async def _resolve_subtitles(
    scope: ExecutionScope,
    item: MediaItem,
    aid: AId,
    cid: CId,
) -> tuple[SubtitleResource, ...]:
    resp_json = await get_player_info(scope, aid, cid, wbi=not isinstance(item, CheeseEpisode))
    if resp_json is None:
        return ()
    if not data_has_chained_keys(resp_json, ["data", "subtitle", "subtitles"]):
        if not isinstance(item, UgcPage):
            emit_download_report(
                f"无法获取该视频的字幕（{aid}, cid: {cid}），原因：{resp_json.get('message')}",
                ReportLevel.WARNING,
            )
        return ()

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
    return tuple(subtitles)


async def _resolve_danmaku(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
    save_type: DanmakuSaveType,
) -> tuple[DanmakuSourceType, tuple[str, ...]]:
    source_type: DanmakuSourceType = (
        "xml" if save_type == "xml" or not (await get_user_info(scope))["is_login"] else "protobuf"
    )
    if source_type == "xml":
        return source_type, (get_xml_danmaku_url(cid),)

    return source_type, tuple(await get_protobuf_danmaku_urls(scope, aid, cid))


async def resolve_resource_manifest(
    execution: ExecutionScope,
    item: MediaItem,
    scope: Scope,
) -> ResourceManifest:
    """Resolve resource locations for one MediaItem without downloading resource bodies."""

    video = wants_video(scope)
    audio = wants_audio(scope)
    subtitle = wants_subtitle(scope)
    danmaku = wants_danmaku(scope)
    cover = wants_cover(scope)
    chapter_info = wants_chapter_info(scope)
    ai_translation_language = scope.resource.ai_translation_language
    if ai_translation_language is not None and not isinstance(ai_translation_language, str):
        raise ValueError("ai_translation_language must be a string or null")

    videos: tuple[VideoUrlMeta, ...] = ()
    audios: tuple[AudioUrlMeta, ...] = ()
    subtitles: tuple[SubtitleResource, ...] = ()
    chapter_info_url: str | None = None

    if isinstance(item, UgcPage):
        aid = item.aid
        if video or audio:
            videos, audios = await get_ugc_video_playurl(
                execution,
                aid,
                item.cid,
                ai_translation_language,
            )
        if chapter_info:
            chapter_info_url = get_player_info_url(aid, item.cid, wbi=False)
    elif isinstance(item, BangumiEpisode):
        aid = item.aid
        if video or audio:
            videos, audios = await get_bangumi_video_playurl(execution, aid, item.cid)
    elif isinstance(item, CheeseEpisode):
        aid = item.aid
        if video or audio:
            videos, audios = await get_cheese_video_playurl(execution, aid, item.episode_id, item.cid)
    else:
        raise TypeError(f"unsupported media item: {type(item).__name__}")

    if subtitle:
        subtitles = await _resolve_subtitles(execution, item, aid, item.cid)
    if not video:
        videos = ()
    if not audio:
        audios = ()

    danmaku_format = resolve_danmaku_format(scope)
    danmaku_source_type: DanmakuSourceType | None = None
    danmaku_urls: tuple[str, ...] = ()
    if danmaku:
        danmaku_source_type, danmaku_urls = await _resolve_danmaku(
            execution,
            aid,
            item.cid,
            danmaku_format,
        )

    return ResourceManifest(
        videos=videos,
        audios=audios,
        subtitles=subtitles,
        danmaku_source_type=danmaku_source_type,
        danmaku_save_type=danmaku_format if danmaku_urls else None,
        danmaku_urls=danmaku_urls,
        cover_url=item.metadata.thumb if cover and item.metadata.thumb else None,
        chapter_info_url=chapter_info_url,
    )
