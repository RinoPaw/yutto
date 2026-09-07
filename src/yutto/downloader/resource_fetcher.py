from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from yutto.core.operation import ReportLevel, emit_download_report
from yutto.types import MultiLangSubtitle
from yutto.utils.fetcher import Fetcher, unwrap_fetch_result
from yutto.utils.functional import data_has_chained_keys
from yutto.utils.metadata import ChapterInfoData

if TYPE_CHECKING:
    from yutto.core.execution import ExecutionScope
    from yutto.resource import ResourceManifest
    from yutto.utils.danmaku import DanmakuData


@dataclass(frozen=True, slots=True, kw_only=True)
class FetchedResources:
    """Transient resource bodies fetched from a ResourceManifest during execution."""

    danmaku: DanmakuData
    subtitles: tuple[MultiLangSubtitle, ...] = ()
    cover_data: bytes | None = None
    chapter_info_data: tuple[ChapterInfoData, ...] = ()


async def _fetch_subtitle(scope: ExecutionScope, lang: str, url: str) -> MultiLangSubtitle | None:
    subtitle_json = (await Fetcher.fetch_json(scope, url)).value_or(None)
    if subtitle_json is None:
        return None
    return MultiLangSubtitle(lang=lang, lines=subtitle_json["body"])


async def _fetch_danmaku(scope: ExecutionScope, manifest: ResourceManifest) -> DanmakuData:
    source_type = manifest.danmaku_source_type
    save_type = manifest.danmaku_save_type
    if source_type is None or not manifest.danmaku_urls:
        return {"source_type": None, "save_type": None, "data": []}

    if source_type == "xml":
        data = [
            unwrap_fetch_result(await Fetcher.fetch_text(scope, url, encoding="utf-8"))
            for url in manifest.danmaku_urls
        ]
        assert all(item is not None for item in data)
        return {"source_type": source_type, "save_type": save_type, "data": data}

    data = await asyncio.gather(*(Fetcher.fetch_bin(scope, url) for url in manifest.danmaku_urls))
    values = [unwrap_fetch_result(result) for result in data]
    assert all(item is not None for item in values)
    return {"source_type": source_type, "save_type": save_type, "data": values}


async def _fetch_chapter_info(scope: ExecutionScope, url: str | None) -> tuple[ChapterInfoData, ...]:
    if url is None:
        return ()
    resp_json = (await Fetcher.fetch_json(scope, url)).value_or(None)
    if resp_json is None:
        return ()
    if not data_has_chained_keys(resp_json, ["data", "view_points"]):
        emit_download_report("无法获取该视频的章节信息", ReportLevel.WARNING)
        return ()
    return tuple(
        ChapterInfoData(content=item["content"], start=item["from"], end=item["to"])
        for item in resp_json["data"]["view_points"]
    )


async def fetch_resources(scope: ExecutionScope, manifest: ResourceManifest) -> FetchedResources:
    """Fetch every body referenced by a ResourceManifest; do not make download-policy decisions."""

    subtitle_results = await asyncio.gather(*(_fetch_subtitle(scope, lang, url) for lang, url in manifest.subtitles))
    subtitles = tuple(subtitle for subtitle in subtitle_results if subtitle is not None)
    danmaku = await _fetch_danmaku(scope, manifest)
    cover_data = (
        unwrap_fetch_result(await Fetcher.fetch_bin(scope, manifest.cover_url))
        if manifest.cover_url is not None
        else None
    )
    chapter_info_data = await _fetch_chapter_info(scope, manifest.chapter_info_url)
    return FetchedResources(
        danmaku=danmaku,
        subtitles=subtitles,
        cover_data=cover_data,
        chapter_info_data=chapter_info_data,
    )
