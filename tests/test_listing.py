from __future__ import annotations

from pathlib import Path

from yutto.core.request import DownloadRequest
from yutto.listing import filter_media_tree, iter_media_items, resolve_media_path
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
from yutto.source import (
    BangumiEpisodeSource,
    BangumiSeasonSource,
    CheeseSeasonSource,
    UgcCollectionSource,
    UgcSpaceSource,
    UgcVideoSource,
    UgcWatchLaterSource,
)
from yutto.types import AId, BvId, CId, CollectionId, EpisodeId, FId, MId, SeasonId, SeriesId
from yutto.utils.metadata import ItemMetaData


def _request(url: str, *, episodes: str | None = None) -> DownloadRequest:
    data: dict[str, object] = {"source": {"url": url}}
    if episodes is not None:
        data["selection"] = {"episodes": episodes}
    return DownloadRequest.model_validate(data)


def _paths(source, media: Media, request: DownloadRequest) -> list[Path]:
    return [resolve_media_path(source, ancestry, item, request) for ancestry, item in iter_media_items(media)]


def test_ugc_path_uses_page_position_and_parent_video_metadata() -> None:
    avid = BvId("BV1D84y1t76J")
    media = UgcVideo(
        avid=avid,
        metadata=ItemMetaData(title="投稿", owner="UP"),
        items=[UgcPage(page=3, cid=CId("456"), metadata=ItemMetaData(title="P3"))],
    )
    source = UgcVideoSource(id=avid, page=3)

    assert _paths(source, media, _request(avid.to_url())) == [Path("投稿")]
    assert _paths(source, media, _request(avid.to_url(), episodes="3")) == [Path("投稿/P3")]


def test_bangumi_episode_and_season_sources_choose_different_auto_paths() -> None:
    episode = BangumiEpisode(
        index=4,
        episode_id=EpisodeId("1004"),
        avid=BvId("BV1D84y1t76J"),
        cid=CId("456"),
        metadata=ItemMetaData(title="4 第四话"),
    )
    media = BangumiSeason(
        season_id=SeasonId("99"),
        metadata=ItemMetaData(title="番剧", owner="UP"),
        items=[episode],
    )

    direct = _paths(
        BangumiEpisodeSource(id=episode.episode_id),
        media,
        _request(f"https://www.bilibili.com/bangumi/play/ep{episode.episode_id}"),
    )
    season = _paths(
        BangumiSeasonSource(id=media.season_id),
        media,
        _request(f"https://www.bilibili.com/bangumi/play/ss{media.season_id}"),
    )

    assert direct == [Path("4 第四话")]
    assert season == [Path("番剧/4 第四话")]


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

    assert _paths(
        BangumiSeasonSource(id=media.season_id),
        media,
        _request(f"https://www.bilibili.com/bangumi/play/ss{media.season_id}"),
    ) == [Path("番剧/【预告】2 第二话")]
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
    request = DownloadRequest.model_validate(
        {
            "source": {"url": f"https://www.bilibili.com/cheese/play/ss{media.season_id}"},
            "output": {"subpath_template": "{id}-{auto}"},
        }
    )

    assert _paths(CheeseSeasonSource(id=media.season_id), media, request) == [Path("7-课程/第七节")]


def test_nested_ugc_paths_follow_media_hierarchy() -> None:
    single = UgcVideo(
        avid=BvId("BV1D84y1t76J"),
        metadata=ItemMetaData(title="单P", owner="UP"),
        items=[UgcPage(page=1, cid=CId("101"), metadata=ItemMetaData(title="P1"))],
    )
    multi = UgcVideo(
        avid=BvId("BV1D84y1t76K"),
        metadata=ItemMetaData(title="多P", owner="UP"),
        items=[
            UgcPage(page=1, cid=CId("201"), metadata=ItemMetaData(title="第一段")),
            UgcPage(page=2, cid=CId("202"), metadata=ItemMetaData(title="第二段")),
        ],
    )
    request = _request("BV1D84y1t76J", episodes="1~2")

    series = UgcSeries(
        series_id=SeriesId("99"),
        metadata=ItemMetaData(title="系列", owner="UP"),
        items=[multi],
    )
    assert _paths(UgcVideoSource(id=multi.avid), series, request) == [
        Path("系列/多P/第一段"),
        Path("系列/多P/第二段"),
    ]

    collection = UgcCollection(
        collection_id=CollectionId("66"),
        metadata=ItemMetaData(title="合集", owner="UP"),
        items=[single, multi],
    )
    assert _paths(
        UgcCollectionSource(id=collection.collection_id, owner_id=MId("123")),
        collection,
        request,
    ) == [
        Path("合集/单P"),
        Path("合集/多P/第一段"),
        Path("合集/多P/第二段"),
    ]

    favourite = UgcFav(
        fid=FId("88"),
        metadata=ItemMetaData(title="收藏夹", owner="收藏者"),
        items=[single, multi],
    )
    assert _paths(UgcVideoSource(id=single.avid), favourite, request) == [
        Path("收藏者的收藏夹/收藏夹/单P"),
        Path("收藏者的收藏夹/收藏夹/多P/第一段"),
        Path("收藏者的收藏夹/收藏夹/多P/第二段"),
    ]


def test_space_and_watch_later_paths_keep_nested_page_layouts() -> None:
    video = UgcVideo(
        avid=BvId("BV1D84y1t76J"),
        metadata=ItemMetaData(title="投稿", owner="视频UP"),
        items=[UgcPage(page=1, cid=CId("101"), metadata=ItemMetaData(title="P1"))],
    )
    space = UgcSpace(
        mid=MId("123"),
        metadata=ItemMetaData(title="空间UP", owner="空间UP"),
        items=[video],
    )
    watch_later = UgcWatchLater(metadata=ItemMetaData(title="稍后再看"), items=[video])

    assert _paths(
        UgcSpaceSource(id=space.mid),
        space,
        _request("https://space.bilibili.com/123", episodes="1"),
    ) == [Path("空间UP的全部投稿视频/投稿/P1")]
    assert _paths(
        UgcWatchLaterSource(id=AId("1")),
        watch_later,
        _request("https://www.bilibili.com/watchlater", episodes="1"),
    ) == [Path("稍后再看/投稿/P1")]


def test_filter_media_tree_preserves_hierarchy_and_drops_empty_branches() -> None:
    first = UgcVideo(
        avid=BvId("BV1D84y1t76J"),
        metadata=ItemMetaData(title="A"),
        items=[
            UgcPage(page=1, cid=CId("101"), metadata=ItemMetaData(title="A1")),
            UgcPage(page=2, cid=CId("102"), metadata=ItemMetaData(title="A2")),
        ],
    )
    second = UgcVideo(
        avid=BvId("BV1D84y1t76K"),
        metadata=ItemMetaData(title="B"),
        items=[UgcPage(page=1, cid=CId("201"), metadata=ItemMetaData(title="B1"))],
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
