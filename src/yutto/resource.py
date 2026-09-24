from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias, cast

from yutto.api.danmaku import get_protobuf_danmaku_urls, get_xml_danmaku_url
from yutto.api.player import (
    PlayUrlInfo,
    TranslationLanguage,
    get_bangumi_playurl,
    get_cheese_playurl,
    get_player_info_url,
    get_subtitle_info,
    get_ugc_playurl,
)
from yutto.auth import get_user_info
from yutto.exceptions import UnSupportedTypeError
from yutto.media import BangumiEpisode, CheeseEpisode, MediaItem, UgcPage

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.scope import Scope
    from yutto.types import AId, AudioUrlMeta, CId, EpisodeId, VideoUrlMeta
    from yutto.utils.danmaku import DanmakuSaveType, DanmakuSourceType

SubtitleResource: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceManifest:
    """Resolved facts for resources requested from one MediaItem; contains no fetched resource bodies."""

    videos: tuple[VideoUrlMeta, ...] = ()
    audios: tuple[AudioUrlMeta, ...] = ()
    subtitles: tuple[SubtitleResource, ...] = ()
    danmaku_source_type: DanmakuSourceType | None = None
    danmaku_urls: tuple[str, ...] = ()
    cover_url: str | None = None
    chapter_info_url: str | None = None
    translation_languages: tuple[TranslationLanguage, ...] = ()
    is_preview: bool = False
    subtitle_unavailable_reason: str | None = None
    invalid_subtitle_languages: tuple[str, ...] = ()


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


async def get_ugc_video_playurl(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
    ai_translation_language: str | None = None,
) -> PlayUrlInfo:
    return await get_ugc_playurl(scope, aid, cid, ai_translation_language)


async def get_bangumi_video_playurl(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
) -> PlayUrlInfo:
    play_url = await get_bangumi_playurl(scope, aid, cid)
    if play_url.is_drm:
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）使用 DRM 保护，当前暂不支持处理 DRM 媒体")
    return play_url


async def get_cheese_video_playurl(
    scope: ExecutionScope,
    aid: AId,
    episode_id: EpisodeId,
    cid: CId,
) -> PlayUrlInfo:
    return await get_cheese_playurl(scope, aid, episode_id, cid)


async def _resolve_subtitles(
    scope: ExecutionScope,
    item: MediaItem,
    aid: AId,
    cid: CId,
) -> tuple[tuple[SubtitleResource, ...], str | None, tuple[str, ...]]:
    info = await get_subtitle_info(scope, aid, cid, wbi=not isinstance(item, CheeseEpisode))
    if info is None:
        return (), None, ()
    if info.tracks is None:
        return (), info.message, ()
    return (
        tuple((track.language, track.url) for track in info.tracks),
        None,
        info.invalid_languages,
    )


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
    """Resolve requested resource facts for one MediaItem without downloading resource bodies."""

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
    translation_languages: tuple[TranslationLanguage, ...] = ()
    is_preview = False
    subtitle_unavailable_reason: str | None = None
    invalid_subtitle_languages: tuple[str, ...] = ()

    if isinstance(item, UgcPage):
        aid = item.aid
        if video or audio:
            play_url = await get_ugc_video_playurl(
                execution,
                aid,
                item.cid,
                ai_translation_language,
            )
            videos = play_url.videos
            audios = play_url.audios
            translation_languages = play_url.translation_languages
            is_preview = play_url.is_preview
        if chapter_info:
            chapter_info_url = get_player_info_url(aid, item.cid, wbi=False)
    elif isinstance(item, BangumiEpisode):
        aid = item.aid
        if video or audio:
            play_url = await get_bangumi_video_playurl(execution, aid, item.cid)
            videos = play_url.videos
            audios = play_url.audios
            is_preview = play_url.is_preview
    elif isinstance(item, CheeseEpisode):
        aid = item.aid
        if video or audio:
            play_url = await get_cheese_video_playurl(execution, aid, item.episode_id, item.cid)
            videos = play_url.videos
            audios = play_url.audios
            is_preview = play_url.is_preview
    else:
        raise TypeError(f"unsupported media item: {type(item).__name__}")

    if subtitle:
        subtitles, subtitle_unavailable_reason, invalid_subtitle_languages = await _resolve_subtitles(
            execution,
            item,
            aid,
            item.cid,
        )
    if not video:
        videos = ()
    if not audio:
        audios = ()

    danmaku_source_type: DanmakuSourceType | None = None
    danmaku_urls: tuple[str, ...] = ()
    if danmaku:
        danmaku_format = resolve_danmaku_format(scope)
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
        danmaku_urls=danmaku_urls,
        cover_url=item.metadata.thumb if cover and item.metadata.thumb else None,
        chapter_info_url=chapter_info_url,
        translation_languages=translation_languages,
        is_preview=is_preview,
        subtitle_unavailable_reason=subtitle_unavailable_reason,
        invalid_subtitle_languages=invalid_subtitle_languages,
    )
