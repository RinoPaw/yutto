from __future__ import annotations

from dataclasses import dataclass, replace
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

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from yutto.path_templates import PathTemplateVariableDict
    from yutto.types import AId
    from yutto.utils.filter import PublicationTimeFilter

MediaAncestry: TypeAlias = tuple[MediaContainer, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PathOptions:
    subpath_template: str = "{auto}"


@dataclass(frozen=True, slots=True)
class ResolvedMediaPath:
    ancestry: MediaAncestry
    item: MediaItem
    path: Path


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


def _filter_media_tree(
    media: Media,
    predicate: Callable[[MediaAncestry, MediaItem], bool],
    ancestry: MediaAncestry,
    *,
    preserve_container: bool,
) -> Media | None:
    if isinstance(media, MediaContainer):
        child_ancestry = (*ancestry, media)
        items = [
            filtered
            for child in media.items
            if (
                filtered := _filter_media_tree(
                    child,
                    predicate,
                    child_ancestry,
                    preserve_container=False,
                )
            )
            is not None
        ]
        if items or preserve_container:
            return replace(media, items=items)
        return None
    if isinstance(media, MediaItem):
        return media if predicate(ancestry, media) else None
    raise TypeError(f"unsupported media: {type(media).__name__}")


def filter_media_tree(
    media: Media,
    predicate: Callable[[MediaAncestry, MediaItem], bool],
) -> Media | None:
    """Filter Media leaves while retaining an empty root container when possible."""
    return _filter_media_tree(
        media,
        predicate,
        (),
        preserve_container=isinstance(media, MediaContainer),
    )


def media_item_pubdate(ancestry: MediaAncestry, item: MediaItem) -> int:
    if item.metadata.premiered:
        return item.metadata.premiered
    if ancestry:
        return ancestry[-1].metadata.premiered
    return 0


def filter_media_by_publication_time(
    media: Media,
    publication_time_filter: PublicationTimeFilter,
) -> Media | None:
    """Filter downloadable leaves by publication time without discarding an empty root container."""
    return filter_media_tree(
        media,
        lambda ancestry, item: publication_time_filter.matches(media_item_pubdate(ancestry, item)),
    )


def _owner(media: MediaItem, parent: MediaContainer | None) -> tuple[str, str]:
    owner = media.metadata.owner or (parent.metadata.owner if parent is not None else "")
    mid = media.metadata.mid or (parent.metadata.mid if parent is not None else None)
    return owner or UNKNOWN, str(mid) if mid is not None else UNKNOWN


def _path_variables(
    parent: BangumiSeason | CheeseSeason | UgcVideo | None,
    item: BangumiEpisode | CheeseEpisode | UgcPage,
    aid: AId,
    *,
    index: int,
    name: str | None = None,
    title: str | None = None,
    username: str | None = None,
    series_title: str | None = None,
) -> PathTemplateVariableDict:
    owner, owner_uid = _owner(item, parent)
    parent_metadata = parent.metadata if parent is not None else None
    pubdate = item.metadata.premiered or (parent_metadata.premiered if parent_metadata is not None else 0)
    download_date = item.metadata.dateadded or (parent_metadata.dateadded if parent_metadata is not None else 0)
    default_title = (
        parent_metadata.title if parent_metadata is not None else (item.metadata.show_title or item.metadata.title)
    )
    return {
        "id": index,
        "aid": str(aid),
        "bvid": str(aid.as_bvid()),
        "name": item.metadata.title if name is None else name,
        "title": default_title if title is None else title,
        "username": owner if username is None else username,
        "series_title": UNKNOWN if series_title is None else series_title,
        "pubdate": pubdate or UNKNOWN,
        "download_date": download_date or UNKNOWN,
        "owner_uid": owner_uid,
        "owner_uname": owner,
    }


def _ugc_context(
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
        auto_path = "{title}/{name}" if video.page_count > 1 else "{title}"
        return video, auto_path, name, title, username, series_title

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


def _resolve_media_path(
    ancestry: MediaAncestry,
    item: MediaItem,
    options: PathOptions,
) -> Path:
    if isinstance(item, UgcPage):
        video, auto_path, name, title, username, series_title = _ugc_context(ancestry, item)
        variables = _path_variables(
            video,
            item,
            video.aid,
            index=item.page,
            name=name,
            title=title,
            username=username,
            series_title=series_title,
        )
        return Path(resolve_path_template(options.subpath_template, auto_path, variables))

    if isinstance(item, BangumiEpisode):
        parent = ancestry[-1] if ancestry else None
        if parent is not None and not isinstance(parent, BangumiSeason):
            raise TypeError("BangumiEpisode parent must be BangumiSeason")
        aid = item.aid
        index = item.index
    elif isinstance(item, CheeseEpisode):
        parent = ancestry[-1] if ancestry else None
        if parent is not None and not isinstance(parent, CheeseSeason):
            raise TypeError("CheeseEpisode parent must be CheeseSeason")
        aid = item.aid
        index = item.index
    else:
        raise TypeError(f"unsupported media item: {type(item).__name__}")

    variables = _path_variables(parent, item, aid, index=index, name=_episode_name(item))
    auto_path = "{name}" if parent is None else "{title}/{name}"
    return Path(resolve_path_template(options.subpath_template, auto_path, variables))


def resolve_media_paths(
    root_media: Media,
    path_options: PathOptions,
) -> tuple[ResolvedMediaPath, ...]:
    """Resolve paths for every downloadable leaf in a Media tree."""
    return tuple(
        ResolvedMediaPath(
            ancestry=ancestry,
            item=item,
            path=_resolve_media_path(ancestry, item, path_options),
        )
        for ancestry, item in iter_media_items(root_media)
    )


__all__ = [
    "MediaAncestry",
    "PathOptions",
    "ResolvedMediaPath",
    "filter_media_by_publication_time",
    "filter_media_tree",
    "iter_media_items",
    "media_item_pubdate",
    "resolve_media_paths",
]
