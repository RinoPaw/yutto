from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias

from yutto.media import (
    BangumiEpisode,
    BangumiSeason,
    CheeseEpisode,
    CheeseSeason,
    Media,
    MediaContainer,
    MediaItem,
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
    from collections.abc import Callable

    from yutto.core.request import DownloadRequest
    from yutto.path_templates import PathTemplateVariableDict
    from yutto.source import MediaSource
    from yutto.types import AvId

MediaAncestry: TypeAlias = tuple[MediaContainer, ...]


def iter_media_items(
    media: Media,
    ancestry: MediaAncestry = (),
) -> Iterator[tuple[MediaAncestry, MediaItem]]:
    if isinstance(media, MediaContainer):
        child_ancestry = (*ancestry, media)
        for child in media.items:
            yield from iter_media_items(child, child_ancestry)
        return
    if isinstance(media, MediaItem):
        yield ancestry, media
        return
    raise TypeError(f"unsupported media: {type(media).__name__}")


def filter_media_tree(
    media: Media,
    predicate: Callable[[MediaAncestry, MediaItem], bool],
    ancestry: MediaAncestry = (),
) -> Media | None:
    if isinstance(media, MediaContainer):
        child_ancestry = (*ancestry, media)
        items = [
            filtered
            for child in media.items
            if (filtered := filter_media_tree(child, predicate, child_ancestry)) is not None
        ]
        return replace(media, items=items) if items else None
    if isinstance(media, MediaItem):
        return media if predicate(ancestry, media) else None
    raise TypeError(f"unsupported media: {type(media).__name__}")


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


def _ugc_context(
    source: MediaSource,
    request: DownloadRequest,
    ancestry: MediaAncestry,
    page: UgcPage,
) -> tuple[UgcVideo, str, str, str, str | None, str | None]:
    if not ancestry or not isinstance(ancestry[-1], UgcVideo):
        raise TypeError("UgcPage parent must be UgcVideo")

    video = ancestry[-1]
    name = page.metadata.title
    title = video.metadata.title
    username: str | None = None
    series_title: str | None = None

    if len(ancestry) == 1:
        return video, _auto_path_template(source, request, video), name, title, username, series_title

    root = ancestry[-2]
    if isinstance(root, UgcSeries):
        auto_path = "{series_title}/{title}/{name}"
        username = root.metadata.owner or video.metadata.owner
        series_title = root.metadata.title
    elif isinstance(root, UgcCollection):
        multi_page = len(video.items) > 1
        auto_path = "{series_title}/{title}/{name}" if multi_page else "{series_title}/{title}"
        username = root.metadata.owner or video.metadata.owner
        series_title = root.metadata.title
    elif isinstance(root, UgcFav):
        multi_page = len(video.items) > 1
        auto_path = (
            "{username}的收藏夹/{series_title}/{title}/{name}"
            if multi_page
            else "{username}的收藏夹/{series_title}/{title}"
        )
        username = root.metadata.owner or video.metadata.owner
        series_title = root.metadata.title
        if not multi_page:
            name = video.metadata.title
    elif isinstance(root, UgcSpace):
        auto_path = "{username}的全部投稿视频/{title}/{name}"
        username = root.metadata.owner or root.metadata.title
    elif isinstance(root, UgcWatchLater):
        auto_path = "稍后再看/{title}/{name}"
        username = ""
        series_title = root.metadata.title
    else:
        raise TypeError(f"unsupported UGC parent: {type(root).__name__}")

    return video, auto_path, name, title, username, series_title


def _episode_name(item: BangumiEpisode | CheeseEpisode) -> str:
    name = item.metadata.title
    if isinstance(item, BangumiEpisode) and item.is_preview:
        return f"【预告】{name}"
    return name


def media_item_pubdate(ancestry: MediaAncestry, item: MediaItem) -> int:
    if item.metadata.premiered:
        return item.metadata.premiered
    if ancestry:
        return ancestry[-1].metadata.premiered
    return 0


def resolve_media_path(
    source: MediaSource,
    ancestry: MediaAncestry,
    item: MediaItem,
    request: DownloadRequest,
) -> Path:
    if isinstance(item, UgcPage):
        video, auto_path, name, title, username, series_title = _ugc_context(source, request, ancestry, item)
        variables = _path_variables(
            video,
            item,
            video.avid,
            index=item.page,
            name=name,
            title=title,
            username=username,
            series_title=series_title,
        )
        return Path(resolve_path_template(request.output.subpath_template, auto_path, variables))

    if isinstance(item, BangumiEpisode):
        if not ancestry or not isinstance(ancestry[-1], BangumiSeason):
            raise TypeError("BangumiEpisode parent must be BangumiSeason")
        parent = ancestry[-1]
        avid = item.avid
        index = item.index
    elif isinstance(item, CheeseEpisode):
        if not ancestry or not isinstance(ancestry[-1], CheeseSeason):
            raise TypeError("CheeseEpisode parent must be CheeseSeason")
        parent = ancestry[-1]
        avid = item.avid
        index = item.index
    else:
        raise TypeError(f"unsupported media item: {type(item).__name__}")

    variables = _path_variables(parent, item, avid, index=index, name=_episode_name(item))
    return Path(
        resolve_path_template(
            request.output.subpath_template,
            _auto_path_template(source, request, parent),
            variables,
        )
    )
