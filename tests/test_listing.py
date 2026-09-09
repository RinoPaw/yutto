from __future__ import annotations

from pathlib import Path

from yutto.listing import (
    PathOptions,
    filter_media_by_publication_time,
    filter_media_tree,
    resolve_media_paths,
)
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
from yutto.types import AId, BvId, CId, CollectionId, EpisodeId, FId, MId, SeasonId, SeriesId
from yutto.utils.filter import PublicationTimeFilter
from yutto.utils.metadata import ItemMetaData


def _paths(media: Media, *, template: str = "{auto}") -> list[Path]:
    return [entry.path for entry in resolve_media_paths(media, PathOptions(subpath_template=template))]


def test_root_ugc_path_uses_media_tree_shape() -> None:
    avid = BvId("BV1D84y1t76J")
    single = UgcVideo(
        avid=avid,
        metadata=ItemMetaData(title="投稿", owner="UP"),
        items=[UgcPage(avid=avid, page=3, cid=CId("456"), metadata=ItemMetaData(title="P3"))],
    )
    multi = UgcVideo(
        avid=avid,
        metadata=ItemMetaData(title="投稿", owner="UP"),
        items=[
            UgcPage(avid=avid, page=1, cid=CId("451"), metadata=ItemMetaData(title="P1")),
            UgcPage(avid=avid, page=3, cid=CId("456"), metadata=ItemMetaData(title="P3")),
        ],
    )

    assert _paths(single) == [Path("投稿")]
    assert _paths(multi) == [Path("投稿/P1"), Path("投稿/P3")]


def test_direct_episode_and_season_tree_shapes_choose_different_auto_paths() -> None:
    episode = BangumiEpisode(
        index=4,
        episode_id=EpisodeId("1004"),
        avid=BvId("BV1D84y1t76J"),
        cid=CId("456"),
        metadata=ItemMetaData(title="4 第四话"),
    )
    season = BangumiSeason(
        season_id=SeasonId("99"),
        metadata=ItemMetaData(title="番剧", owner="UP"),
        items=[episode],
    )

    assert _paths(episode) == [Path("4 第四话")]
    assert _paths(season) == [Path("番剧/4 第四话")]


def test_bangumi_preview_prefixes_path_without_mutating_metadata() -> None:
    episode = BangumiEpisode(
        index=2,
        episode_id=EpisodeId("1002"),
        avid=BvId("BV1D84y1t76J"),
        cid=CId("456"),
        is_preview=True,
        metadata=ItemMetaData(title="2 第二话"),
    )
    media = BangumiSeason(
        season_id=SeasonId("99"),
        metadata=ItemMetaData(title="番剧"),
        items=[episode],
    )

    assert _paths(media) == [Path("番剧/【预告】2 第二话")]
    assert episode.metadata.title == "2 第二话"


def test_cheese_path_uses_original_episode_index() -> None:
    episode = CheeseEpisode(
        index=7,
        episode_id=EpisodeId("7007"),
        avid=AId("123"),
        cid=CId("456"),
        metadata=ItemMetaData(title="第七节"),
    )
    media = CheeseSeason(
        season_id=SeasonId("77"),
        metadata=ItemMetaData(title="课程"),
        items=[episode],
    )

    assert _paths(media, template="{id}-{auto}") == [Path("7-课程/第七节")]


def test_nested_ugc_paths_follow_media_hierarchy() -> None:
    single_avid = BvId("BV1D84y1t76J")
    single = UgcVideo(
        avid=single_avid,
        metadata=ItemMetaData(title="单P", owner="UP"),
        items=[UgcPage(avid=single_avid, page=1, cid=CId("101"), metadata=ItemMetaData(title="P1"))],
    )
    multi_avid = BvId("BV1D84y1t76K")
    multi = UgcVideo(
        avid=multi_avid,
        metadata=ItemMetaData(title="多P", owner="UP"),
        items=[
            UgcPage(avid=multi_avid, page=1, cid=CId("201"), metadata=ItemMetaData(title="第一段")),
            UgcPage(avid=multi_avid, page=2, cid=CId("202"), metadata=ItemMetaData(title="第二段")),
        ],
    )

    series = UgcSeries(
        series_id=SeriesId("99"),
        metadata=ItemMetaData(title="系列", owner="UP"),
        items=[multi],
    )
    assert _paths(series) == [
        Path("系列/多P/第一段"),
        Path("系列/多P/第二段"),
    ]

    collection = UgcCollection(
        collection_id=CollectionId("66"),
        metadata=ItemMetaData(title="合集", owner="UP"),
        items=[single, multi],
    )
    assert _paths(collection) == [
        Path("合集/单P"),
        Path("合集/多P/第一段"),
        Path("合集/多P/第二段"),
    ]

    favourite = UgcFav(
        fid=FId("88"),
        metadata=ItemMetaData(title="收藏夹", owner="收藏者"),
        items=[single, multi],
    )
    assert _paths(favourite) == [
        Path("收藏者的收藏夹/收藏夹/单P"),
        Path("收藏者的收藏夹/收藏夹/多P/第一段"),
        Path("收藏者的收藏夹/收藏夹/多P/第二段"),
    ]


def test_space_and_watch_later_paths_keep_nested_page_layouts() -> None:
    avid = BvId("BV1D84y1t76J")
    video = UgcVideo(
        avid=avid,
        metadata=ItemMetaData(title="投稿", owner="视频UP"),
        items=[UgcPage(avid=avid, page=1, cid=CId("101"), metadata=ItemMetaData(title="P1"))],
    )
    space = UgcSpace(
        mid=MId("123"),
        metadata=ItemMetaData(title="空间UP", owner="空间UP"),
        items=[video],
    )
    watch_later = UgcWatchLater(metadata=ItemMetaData(title="稍后再看"), items=[video])

    assert _paths(space) == [Path("空间UP的全部投稿视频/投稿/P1")]
    assert _paths(watch_later) == [Path("稍后再看/投稿/P1")]


def test_filter_media_tree_preserves_hierarchy_and_drops_empty_nested_branches() -> None:
    first_avid = BvId("BV1D84y1t76J")
    first = UgcVideo(
        avid=first_avid,
        metadata=ItemMetaData(title="A"),
        items=[
            UgcPage(avid=first_avid, page=1, cid=CId("101"), metadata=ItemMetaData(title="A1")),
            UgcPage(avid=first_avid, page=2, cid=CId("102"), metadata=ItemMetaData(title="A2")),
        ],
    )
    second_avid = BvId("BV1D84y1t76K")
    second = UgcVideo(
        avid=second_avid,
        metadata=ItemMetaData(title="B"),
        items=[UgcPage(avid=second_avid, page=1, cid=CId("201"), metadata=ItemMetaData(title="B1"))],
    )
    root = UgcSeries(
        series_id=SeriesId("99"),
        metadata=ItemMetaData(title="系列"),
        items=[first, second],
    )

    filtered = filter_media_tree(root, lambda ancestry, item: item.metadata.title == "A2")

    assert isinstance(filtered, UgcSeries)
    assert len(filtered.items) == 1
    assert filtered.items[0].metadata.title == "A"
    assert [page.metadata.title for page in filtered.items[0].items] == ["A2"]
    assert root.items == [first, second]


def test_publication_filter_keeps_empty_root_container() -> None:
    avid = BvId("BV1D84y1t76J")
    root = UgcSeries(
        series_id=SeriesId("99"),
        metadata=ItemMetaData(title="系列"),
        items=[
            UgcVideo(
                avid=avid,
                metadata=ItemMetaData(title="A"),
                items=[
                    UgcPage(
                        avid=avid,
                        page=1,
                        cid=CId("101"),
                        metadata=ItemMetaData(title="A1", premiered=1_700_000_000),
                    )
                ],
            )
        ],
    )
    publication_filter = PublicationTimeFilter.from_strings("2026-01-01", "2027-01-01")

    filtered = filter_media_by_publication_time(root, publication_filter)

    assert isinstance(filtered, UgcSeries)
    assert filtered.items == []
