from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

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
    from yutto.config import ResolvedConfig
    from yutto.core.execution import ExecutionScope
    from yutto.types import AId, AudioUrlMeta, CId, VideoUrlMeta
    from yutto.utils.danmaku import DanmakuSaveType, DanmakuSourceType

SubtitleResource: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceManifest:
    """Resolved facts for resources requested from one MediaItem; contains no fetched resource bodies."""

    video_requested: bool = False
    audio_requested: bool = False
    subtitle_requested: bool = False
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


def wants_video(config: ResolvedConfig) -> bool:
    return config.resource.video


def wants_audio(config: ResolvedConfig) -> bool:
    return config.resource.audio


def wants_danmaku(config: ResolvedConfig) -> bool:
    return config.resource.danmaku


def wants_subtitle(config: ResolvedConfig) -> bool:
    return config.resource.subtitle


def wants_metadata(config: ResolvedConfig) -> bool:
    return config.resource.metadata


def wants_cover(config: ResolvedConfig) -> bool:
    return config.resource.cover


def wants_chapter_info(config: ResolvedConfig) -> bool:
    return config.resource.chapter_info


def should_save_cover(config: ResolvedConfig) -> bool:
    cover = wants_cover(config)
    save_cover = config.resource.save_cover
    if save_cover and not cover:
        raise ValueError("save_cover requires cover")
    if cover and not any(
        (
            wants_video(config),
            wants_audio(config),
            wants_danmaku(config),
            wants_subtitle(config),
            wants_metadata(config),
            wants_chapter_info(config),
        )
    ):
        return True
    return save_cover


def resolve_danmaku_format(config: ResolvedConfig) -> DanmakuSaveType:
    value = config.danmaku.format
    if value not in {"xml", "ass", "protobuf"}:
        raise ValueError(f"unsupported danmaku format: {value}")
    return value


async def get_bangumi_video_playurl(
    scope: ExecutionScope,
    aid: AId,
    cid: CId,
) -> PlayUrlInfo:
    play_url = await get_bangumi_playurl(scope, aid, cid)
    if play_url.is_drm:
        raise UnSupportedTypeError(f"该视频（{aid}, cid: {cid}）使用 DRM 保护，当前暂不支持处理 DRM 媒体")
    return play_url


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
    config: ResolvedConfig,
) -> ResourceManifest:
    """Resolve requested resource facts for one MediaItem without downloading resource bodies."""

    video = wants_video(config)
    audio = wants_audio(config)
    subtitle = wants_subtitle(config)
    danmaku = wants_danmaku(config)
    cover = wants_cover(config)
    chapter_info = wants_chapter_info(config)
    ai_translation_language = config.resource.ai_translation_language

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
            play_url = await get_ugc_playurl(execution, aid, item.cid, ai_translation_language)
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
            play_url = await get_cheese_playurl(execution, aid, item.episode_id, item.cid)
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
        danmaku_format = resolve_danmaku_format(config)
        danmaku_source_type, danmaku_urls = await _resolve_danmaku(execution, aid, item.cid, danmaku_format)

    return ResourceManifest(
        video_requested=video,
        audio_requested=audio,
        subtitle_requested=subtitle,
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
