from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from yutto.api.bangumi import get_bangumi_playurl, get_bangumi_subtitles
from yutto.api.cheese import get_cheese_playurl, get_cheese_subtitles
from yutto.api.danmaku import get_danmaku
from yutto.api.ugc_video import get_ugc_video_chapters, get_ugc_video_playurl, get_ugc_video_subtitles
from yutto.media import BangumiEpisode, CheeseEpisode, MediaItem, UgcPage
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.types import AudioUrlMeta, MultiLangSubtitle, VideoUrlMeta
    from yutto.utils.danmaku import DanmakuData
    from yutto.utils.metadata import ChapterInfoData, ItemMetaData


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceOptions:
    video: bool = True
    audio: bool = True
    danmaku: bool = True
    subtitle: bool = True
    metadata: bool = False
    cover: bool = True
    chapter_info: bool = True
    ai_translation_language: str | None = None
    danmaku_format: Literal["xml", "ass", "protobuf"] = "ass"


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadableEntry:
    title: str
    videos: tuple[VideoUrlMeta, ...]
    audios: tuple[AudioUrlMeta, ...]
    subtitles: tuple[MultiLangSubtitle, ...]
    metadata: ItemMetaData | None
    danmaku: DanmakuData
    cover_data: bytes | None
    chapter_info_data: tuple[ChapterInfoData, ...]


async def resolve_media_item(
    scope: ExecutionScope,
    item: MediaItem,
    options: ResourceOptions,
) -> DownloadableEntry:
    videos: list[VideoUrlMeta] = []
    audios: list[AudioUrlMeta] = []
    subtitles: list[MultiLangSubtitle] = []
    chapters: list[ChapterInfoData] = []

    if isinstance(item, UgcPage):
        if options.video or options.audio:
            videos, audios = await get_ugc_video_playurl(
                scope,
                item.avid,
                item.cid,
                options.ai_translation_language,
            )
        if options.subtitle:
            subtitles = await get_ugc_video_subtitles(scope, item.avid, item.cid)
        if options.chapter_info:
            chapters = await get_ugc_video_chapters(scope, item.avid, item.cid)
    elif isinstance(item, BangumiEpisode):
        if options.video or options.audio:
            videos, audios = await get_bangumi_playurl(scope, item.avid, item.cid)
        if options.subtitle:
            subtitles = await get_bangumi_subtitles(scope, item.avid, item.cid)
    elif isinstance(item, CheeseEpisode):
        if options.video or options.audio:
            videos, audios = await get_cheese_playurl(scope, item.avid, item.episode_id, item.cid)
        if options.subtitle:
            subtitles = await get_cheese_subtitles(scope, item.avid, item.cid)
    else:
        raise TypeError(f"unsupported media item: {type(item).__name__}")

    if not options.video:
        videos = []
    if not options.audio:
        audios = []

    danmaku: DanmakuData = {"source_type": None, "save_type": None, "data": []}
    if options.danmaku:
        danmaku = await get_danmaku(scope, item.cid, item.avid, options.danmaku_format)

    cover_data = None
    if options.cover and item.cover_url:
        cover_data = unwrap_fetch_result(await Fetcher.fetch_bin(scope, item.cover_url))

    return DownloadableEntry(
        title=item.title,
        videos=tuple(videos),
        audios=tuple(audios),
        subtitles=tuple(subtitles),
        metadata=item.extraMetaData if options.metadata else None,
        danmaku=danmaku,
        cover_data=cover_data,
        chapter_info_data=tuple(chapters),
    )
