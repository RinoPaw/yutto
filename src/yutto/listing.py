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
    UgcFavEntry,
    UgcPage,
    UgcSeries,
    UgcSpace,
    UgcVideo,
    UgcWatchLater,
)
from yutto.path_templates import UNKNOWN, resolve_path_template

if TYPE_CHECKING:
    from collections.abc import Iterator

    from yutto.path_templates import PathTemplateVariableDict
    from yutto.types import AId

MediaAncestry: TypeAlias = tuple[MediaContainer | UgcFavEntry, ...]


@dataclass(frozen=True, slots=True)
class ResolvedMediaPath:
    ancestry: MediaAncestry
    item: MediaItem
    path: Path


def iter_media_items(
    media: Media,
    ancestry: MediaAncestry = (),
) -> Iterator[tuple[MediaAncestry, MediaItem]]:
    if isinstance(media, UgcFavEntry):
        yield from iter_media_items(media.video, (*ancestry, media))
        return
    if isinstance(media, MediaContainer):
        child_ancestry = (*ancestry, media)
        for child in media.items:
            yield from iter_media_items(child, child_ancestry)
        return
    if isinstance(media, MediaItem):
        yield ancestry, media
        return
    raise TypeError(f"unsupported media: {type(media).__name__}")


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
    pubdate = item.metadata.published_at or (parent_metadata.published_at if parent_metadata is not None else 0)
    download_date = item.metadata.added_at or (parent_metadata.added_at if parent_metadata is not None else 0)
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
    favourite_entry = ancestry[-2] if len(ancestry) >= 2 and isinstance(ancestry[-2], UgcFavEntry) else None
    name = page.metadata.title
    title = (
        favourite_entry.metadata.title or video.metadata.title
        if favourite_entry is not None
        else video.metadata.title
    )
    username: str | None = None
    series_title: str | None = None

    if len(ancestry) == 1:
        auto_path = "{title}/{name}" if video.page_count > 1 else "{title}"
        return video, auto_path, name, title, username, series_title

    root_index = -3 if favourite_entry is not None else -2
    if len(ancestry) < abs(root_index):
        raise TypeError("UgcVideo container ancestry is incomplete")
    root = ancestry[root_index]
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
        if favourite_entry is None:
            raise TypeError("UgcFav child must carry UgcFavEntry context")
        multi_page = len(video.items) > 1
        auto_path = (
            "{username}的收藏夹/{series_title}/{title}/{name}"
            if multi_page
            else "{username}的收藏夹/{series_title}/{title}"
        )
        username = root.metadata.owner or video.metadata.owner
        series_title = root.metadata.title
        if not multi_page:
            name = title
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


def _contextualize_item(ancestry: MediaAncestry, item: MediaItem) -> MediaItem:
    if not isinstance(item, UgcPage) or len(ancestry) < 3:
        return item

    root = ancestry[-3]
    favourite_entry = ancestry[-2]
    video = ancestry[-1]
    if (
        isinstance(root, UgcFav)
        and isinstance(favourite_entry, UgcFavEntry)
        and isinstance(video, UgcVideo)
        and len(video.items) == 1
    ):
        title = favourite_entry.metadata.title or video.metadata.title
        return replace(
            item,
            metadata=replace(item.metadata, title=title, show_title=title),
        )
    return item


def _episode_name(item: BangumiEpisode | CheeseEpisode) -> str:
    name = item.metadata.title
    if isinstance(item, BangumiEpisode) and item.is_preview:
        return f"【预告】{name}"
    return name


def _resolve_media_path(
    ancestry: MediaAncestry,
    item: MediaItem,
    subpath_template: str,
) -> Path:
    if isinstance(item, UgcPage):
        video, auto_path, name, title, username, series_title = _ugc_context(ancestry, item)
        variables = _path_variables(
            video,
            item,
            video.aid,
            index=item.index,
            name=name,
            title=title,
            username=username,
            series_title=series_title,
        )
        return Path(resolve_path_template(subpath_template, auto_path, variables))

    if isinstance(item, BangumiEpisode):
        parent = ancestry[-1] if ancestry else None
        if parent is not None and not isinstance(parent, BangumiSeason):
            raise TypeError("BangumiEpisode parent must be BangumiSeason")
        aid = item.aid
    elif isinstance(item, CheeseEpisode):
        parent = ancestry[-1] if ancestry else None
        if parent is not None and not isinstance(parent, CheeseSeason):
            raise TypeError("CheeseEpisode parent must be CheeseSeason")
        aid = item.aid
    else:
        raise TypeError(f"unsupported media item: {type(item).__name__}")

    variables = _path_variables(parent, item, aid, index=item.index, name=_episode_name(item))
    auto_path = "{name}" if parent is None else "{title}/{name}"
    return Path(resolve_path_template(subpath_template, auto_path, variables))


def resolve_media_paths(
    root_media: Media,
    *,
    subpath_template: str = "{auto}",
) -> tuple[ResolvedMediaPath, ...]:
    """Resolve paths for every downloadable leaf in a Media tree."""
    resolved: list[ResolvedMediaPath] = []
    for ancestry, item in iter_media_items(root_media):
        contextual_item = _contextualize_item(ancestry, item)
        resolved.append(
            ResolvedMediaPath(
                ancestry=ancestry,
                item=contextual_item,
                path=_resolve_media_path(ancestry, contextual_item, subpath_template),
            )
        )
    return tuple(resolved)


__all__ = [
    "MediaAncestry",
    "ResolvedMediaPath",
    "iter_media_items",
    "resolve_media_paths",
]
