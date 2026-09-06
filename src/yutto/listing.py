from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from yutto.core.result import ResolvedItem
from yutto.media import (
    BangumiEpisode,
    BangumiSeason,
    CheeseEpisode,
    CheeseSeason,
    UgcCollection,
    UgcFav,
    UgcPage,
    UgcSeries,
    UgcSpace,
    UgcVideo,
    UgcWatchLater,
)
from yutto.path_templates import UNKNOWN, resolve_path_template
from yutto.source import AmbiguousSource, BangumiEpisodeSource, CheeseEpisodeSource
from yutto.types import EpisodeId

if TYPE_CHECKING:
    from yutto.core.request import DownloadRequest
    from yutto.media import MediaContainer, MediaItem
    from yutto.path_templates import PathTemplateVariableDict
    from yutto.source import MediaSource
    from yutto.types import AvId


@dataclass(frozen=True, slots=True)
class ProjectedMediaItem:
    parent: MediaContainer
    item: MediaItem
    listing: ResolvedItem


def _owner(media: MediaItem, parent: BangumiSeason | CheeseSeason | UgcVideo) -> tuple[str, str]:
    owner = media.metadata.owner or parent.metadata.owner
    mid = media.metadata.mid or parent.metadata.mid
    return owner or UNKNOWN, str(mid) if mid is not None else UNKNOWN


def _path_variables(
    parent: BangumiSeason | CheeseSeason | UgcVideo,
    item: BangumiEpisode | CheeseEpisode | UgcPage,
    avid: AvId,
    *,
    index: int,
    name: str | None = None,
    title: str | None = None,
    username: str | None = None,
    series_title: str | None = None,
) -> PathTemplateVariableDict:
    owner, owner_uid = _owner(item, parent)
    pubdate = item.metadata.premiered or parent.metadata.premiered
    download_date = item.metadata.dateadded or parent.metadata.dateadded
    return {
        "id": index,
        "aid": str(avid.as_aid()),
        "bvid": str(avid.as_bvid()),
        "name": item.metadata.title if name is None else name,
        "title": parent.metadata.title if title is None else title,
        "username": owner if username is None else username,
        "series_title": UNKNOWN if series_title is None else series_title,
        "pubdate": pubdate if pubdate else UNKNOWN,
        "download_date": download_date if download_date else UNKNOWN,
        "owner_uid": owner_uid,
        "owner_uname": owner,
    }


def _is_direct_episode_source(source: MediaSource) -> bool:
    if isinstance(source, (BangumiEpisodeSource, CheeseEpisodeSource)):
        return True
    return isinstance(source, AmbiguousSource) and isinstance(source.id, EpisodeId)


def _auto_path_template(
    source: MediaSource,
    request: DownloadRequest,
    parent: BangumiSeason | CheeseSeason | UgcVideo,
) -> str:
    if isinstance(parent, UgcVideo):
        return "{title}" if request.selection.episodes is None else "{title}/{name}"
    if _is_direct_episode_source(source) and request.selection.episodes is None:
        return "{name}"
    return "{title}/{name}"


def _project_item(
    source: MediaSource,
    request: DownloadRequest,
    parent: BangumiSeason | CheeseSeason | UgcVideo,
    item: BangumiEpisode | CheeseEpisode | UgcPage,
) -> ResolvedItem:
    if isinstance(item, UgcPage):
        if not isinstance(parent, UgcVideo):
            raise TypeError("UgcPage parent must be UgcVideo")
        return _project_ugc_page(
            request,
            parent,
            item,
            auto_path_template=_auto_path_template(source, request, parent),
        )
    name = item.metadata.title
    if isinstance(item, BangumiEpisode):
        avid = item.avid
        index = item.index
        url = f"https://www.bilibili.com/bangumi/play/ep{item.episode_id}"
        if item.is_preview:
            name = f"【预告】{name}"
    elif isinstance(item, CheeseEpisode):
        avid = item.avid
        index = item.index
        url = f"https://www.bilibili.com/cheese/play/ep{item.episode_id}"
    else:
        raise TypeError(f"unsupported media item: {type(item).__name__}")

    variables = _path_variables(parent, item, avid, index=index, name=name)
    path = resolve_path_template(
        request.output.subpath_template,
        _auto_path_template(source, request, parent),
        variables,
    )
    uploader = item.metadata.owner or parent.metadata.owner
    description = parent.metadata.plot or item.metadata.plot
    tags = item.metadata.tag or parent.metadata.tag or parent.metadata.genre
    cover_url = item.metadata.thumb or parent.metadata.thumb

    return ResolvedItem(
        avid=avid,
        cid=item.cid,
        url=url,
        name=name,
        title=parent.metadata.title,
        cover_url=cover_url,
        planned_path=Path(path),
        uploader=uploader,
        description=description,
        tags=tuple(tags),
        pubdate=item.metadata.premiered or parent.metadata.premiered,
        duration=item.metadata.duration,
    )


def _project_ugc_page(
    request: DownloadRequest,
    video: UgcVideo,
    page: UgcPage,
    *,
    auto_path_template: str,
    username: str | None = None,
    series_title: str | None = None,
    name: str | None = None,
    title: str | None = None,
    display_group: str | None = None,
) -> ResolvedItem:
    name = page.metadata.title if name is None else name
    title = video.metadata.title if title is None else title
    variables = _path_variables(
        video,
        page,
        video.avid,
        index=page.page,
        name=name,
        title=title,
        username=username,
        series_title=series_title,
    )
    path = resolve_path_template(request.output.subpath_template, auto_path_template, variables)
    return ResolvedItem(
        avid=video.avid,
        cid=page.cid,
        url=f"{video.avid.to_url()}?p={page.page}",
        name=name,
        title=title,
        cover_url=page.metadata.thumb or video.metadata.thumb,
        planned_path=Path(path),
        display_group=display_group,
        uploader=page.metadata.owner or video.metadata.owner,
        description=video.metadata.plot or page.metadata.plot,
        tags=tuple(page.metadata.tag or video.metadata.tag or video.metadata.genre),
        pubdate=page.metadata.premiered or video.metadata.premiered,
        duration=page.metadata.duration,
    )


def _project_nested_ugc(
    request: DownloadRequest,
    root: UgcCollection | UgcFav | UgcSeries | UgcSpace | UgcWatchLater,
) -> tuple[ProjectedMediaItem, ...]:
    entries: list[ProjectedMediaItem] = []
    for video in root.items:
        if isinstance(root, UgcSeries):
            auto_path = "{series_title}/{title}/{name}"
            username = root.metadata.owner or video.metadata.owner
            series_title = root.metadata.title
            single_name = None
            display_group = None
        elif isinstance(root, UgcCollection):
            multi_page = len(video.items) > 1
            auto_path = "{series_title}/{title}/{name}" if multi_page else "{series_title}/{title}"
            username = root.metadata.owner or video.metadata.owner
            series_title = root.metadata.title
            single_name = None
            display_group = None
        elif isinstance(root, UgcFav):
            multi_page = len(video.items) > 1
            auto_path = (
                "{username}的收藏夹/{series_title}/{title}/{name}"
                if multi_page
                else "{username}的收藏夹/{series_title}/{title}"
            )
            username = root.metadata.owner or video.metadata.owner
            series_title = root.metadata.title
            single_name = None if multi_page else video.metadata.title
            display_group = video.metadata.title if multi_page else None
        elif isinstance(root, UgcSpace):
            auto_path = "{username}的全部投稿视频/{title}/{name}"
            username = root.metadata.owner or root.metadata.title
            series_title = None
            single_name = None
            display_group = None
        else:
            auto_path = "稍后再看/{title}/{name}"
            username = ""
            series_title = root.metadata.title
            single_name = None
            display_group = None

        for page in video.items:
            listing = _project_ugc_page(
                request,
                video,
                page,
                auto_path_template=auto_path,
                username=username,
                series_title=series_title,
                name=single_name,
                display_group=display_group,
            )
            entries.append(ProjectedMediaItem(parent=video, item=page, listing=listing))
    return tuple(entries)


def project_media_entries(
    source: MediaSource,
    media: MediaContainer,
    request: DownloadRequest,
) -> tuple[ProjectedMediaItem, ...]:
    if isinstance(media, BangumiSeason):
        return tuple(
            ProjectedMediaItem(parent=media, item=item, listing=_project_item(source, request, media, item))
            for item in media.items
        )
    if isinstance(media, CheeseSeason):
        return tuple(
            ProjectedMediaItem(parent=media, item=item, listing=_project_item(source, request, media, item))
            for item in media.items
        )
    if isinstance(media, UgcVideo):
        return tuple(
            ProjectedMediaItem(parent=media, item=item, listing=_project_item(source, request, media, item))
            for item in media.items
        )
    if isinstance(media, (UgcCollection, UgcFav, UgcSeries, UgcSpace, UgcWatchLater)):
        return _project_nested_ugc(request, media)
    raise TypeError(f"unsupported top-level media: {type(media).__name__}")


def project_media_items(
    source: MediaSource,
    media: MediaContainer,
    request: DownloadRequest,
) -> tuple[ResolvedItem, ...]:
    return tuple(entry.listing for entry in project_media_entries(source, media, request))


__all__ = ["ProjectedMediaItem", "project_media_entries", "project_media_items"]
