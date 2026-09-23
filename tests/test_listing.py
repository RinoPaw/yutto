from __future__ import annotations

from pathlib import Path

from yutto.listing import resolve_media_paths
from yutto.media import (
    BangumiEpisode,
    BangumiSeason,
    CheeseEpisode,
    CheeseSeason,
    Media,
    UgcCollection,
    UgcFav,
    UgcPage,
    UgcSeries,
    UgcSpace,
    UgcVideo,
    UgcWatchLater,
)
from yutto.types import AId, CId, CollectionId, EpisodeId, FId, MId, SeasonId, SeriesId
from yutto.utils.metadata import ItemMetaData


def _paths(media: Media, *, template: str = "{auto}") -> list[Path]:
    return [entry.path for entry in resolve_media_paths(media, subpath_template=template)]


def test_root_ugc_path_uses_original_page_count() -> None:
    aid = AId("808982399")
    single_page = UgcVideo(
        aid=aid,
        page_count=1,
        metadata=ItemMetaData(title="投稿", owner="UP"),
        items=(UgcPage(aid=aid, index=1, cid=CId("451"), metadata=ItemMetaData(title="P1")),),
    )
    selected_from_multi_page = UgcVideo(
        aid=aid,
        page_count=3,
        metadata=ItemMetaData(title="投稿", owner="UP"),
        items=(UgcPage(aid=aid, index=3, cid=CId("456"), metadata=ItemMetaData(title="P3")),),
    )
    multi_selection = UgcVideo(
        aid=aid,
        page_count=3,
        metadata=ItemMetaData(title="投稿", owner="UP"),
        items=(
            UgcPage(aid=aid, index=1, cid=CId("451"), metadata=ItemMetaData(title="P1")),
            UgcPage(aid=aid, index=3, cid=CId("456"), metadata=ItemMetaData(title="P3")),
        ),
    )

    assert _paths(single_page) == [Path("投稿")]
    assert _paths(selected_from_multi_page) == [Path("投稿/P3")]
    assert _paths(multi_selection) == [Path("投稿/P1"), Path("投稿/P3")]


def test_direct_episode_and_season_tree_shapes_choose_different_auto_paths() -> None:
    episode = BangumiEpisode(
        index=4,
        episode_id=EpisodeId("1004"),
        aid=AId("808982399"),
        cid=CId("456"),
        metadata=ItemMetaData(title="4 第四话"),
    )
    season = BangumiSeason(
        season_id=SeasonId("99"),
        metadata=ItemMetaData(title="番剧", owner="UP"),
        items=(episode,),
    )

    assert _paths(episode) == [Path("4 第四话")]
    assert _paths(season) == [Path("番剧/4 第四话")]


def test_bangumi_preview_prefixes_path_without_mutating_metadata() -> None:
    episode = BangumiEpisode(
        index=2,
        episode_id=EpisodeId("1002"),
        aid=AId("808982399"),
        cid=CId("456"),
        is_preview=True,
        metadata=ItemMetaData(title="2 第二话"),
    )
    media = BangumiSeason(
        season_id=SeasonId("99"),
        metadata=ItemMetaData(title="番剧"),
        items=(episode,),
    )

    assert _paths(media) == [Path("番剧/【预告】2 第二话")]
    assert episode.metadata.title == "2 第二话"


def test_cheese_path_uses_original_episode_index() -> None:
    episode = CheeseEpisode(
        index=7,
        episode_id=EpisodeId("7007"),
        aid=AId("123"),
        cid=CId("456"),
        metadata=ItemMetaData(title="第七节"),
    )
    media = CheeseSeason(
        season_id=SeasonId("77"),
        metadata=ItemMetaData(title="课程"),
        items=(episode,),
    )

    assert _paths(media, template="{id}-{auto}") == [Path("7-课程/第七节")]


def test_nested_ugc_paths_follow_media_hierarchy() -> None:
    single_aid = AId("101")
    single = UgcVideo(
        aid=single_aid,
        metadata=ItemMetaData(title="单P", owner="UP"),
        items=(UgcPage(aid=single_aid, index=1, cid=CId("101"), metadata=ItemMetaData(title="P1")),),
    )
    multi_aid = AId("102")
    multi = UgcVideo(
        aid=multi_aid,
        metadata=ItemMetaData(title="多P", owner="UP"),
        items=(
            UgcPage(aid=multi_aid, index=1, cid=CId("201"), metadata=ItemMetaData(title="第一段")),
            UgcPage(aid=multi_aid, index=2, cid=CId("202"), metadata=ItemMetaData(title="第二段")),
        ),
    )

    series = UgcSeries(
        series_id=SeriesId("99"),
        metadata=ItemMetaData(title="系列", owner="UP"),
        items=(multi,),
    )
    assert _paths(series) == [Path("系列/多P/第一段"), Path("系列/多P/第二段")]

    collection = UgcCollection(
        collection_id=CollectionId("66"),
        metadata=ItemMetaData(title="合集", owner="UP"),
        items=(single, multi),
    )
    assert _paths(collection) == [Path("合集/单P"), Path("合集/多P/第一段"), Path("合集/多P/第二段")]

    favourite = UgcFav(
        fid=FId("88"),
        metadata=ItemMetaData(title="收藏夹", owner="收藏者"),
        items=(single, multi),
    )
    assert _paths(favourite) == [
        Path("收藏者的收藏夹/收藏夹/单P"),
        Path("收藏者的收藏夹/收藏夹/多P/第一段"),
        Path("收藏者的收藏夹/收藏夹/多P/第二段"),
    ]


def test_space_and_watch_later_paths_keep_nested_page_layouts() -> None:
    aid = AId("123")
    video = UgcVideo(
        aid=aid,
        metadata=ItemMetaData(title="投稿", owner="视频UP"),
        items=(UgcPage(aid=aid, index=1, cid=CId("101"), metadata=ItemMetaData(title="P1")),),
    )
    space = UgcSpace(
        mid=MId("123"),
        metadata=ItemMetaData(title="空间UP", owner="空间UP"),
        items=(video,),
    )
    watch_later = UgcWatchLater(metadata=ItemMetaData(title="稍后再看"), items=(video,))

    assert _paths(space) == [Path("空间UP的全部投稿视频/投稿/P1")]
    assert _paths(watch_later) == [Path("稍后再看/投稿/P1")]
