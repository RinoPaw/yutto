from __future__ import annotations

from pathlib import Path

from yutto.core.request import DownloadRequest
from yutto.listing import iter_media_items, project_media_items
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


def test_ugc_projection_uses_page_position_and_parent_video_metadata() -> None:
    avid = BvId("BV1D84y1t76J")
    media = UgcVideo(
        avid=avid,
        metadata=ItemMetaData(
            title="投稿",
            plot="简介",
            owner="UP",
            mid=MId("123"),
            thumb="https://img/cover.jpg",
            tag=["标签"],
        ),
        items=[
            UgcPage(
                page=3,
                cid=CId("456"),
                metadata=ItemMetaData(
                    title="P3",
                    premiered=1_700_000_000,
                    duration=30,
                    dateadded=1_700_000_100,
                ),
            )
        ],
    )
    source = UgcVideoSource(id=avid, page=3)

    item = project_media_items(source, media, _request(avid.to_url()))[0]

    assert item.url == f"{avid.to_url()}?p=3"
    assert item.planned_path == Path("投稿")
    assert item.name == "P3"
    assert item.title == "投稿"
    assert item.uploader == "UP"
    assert item.description == "简介"
    assert item.tags == ("标签",)
    assert item.pubdate == 1_700_000_000
    assert item.duration == 30

    selected = project_media_items(source, media, _request(avid.to_url(), episodes="3"))[0]
    assert selected.planned_path == Path("投稿/P3")


def test_bangumi_episode_and_season_sources_choose_different_auto_paths() -> None:
    episode = BangumiEpisode(
        index=4,
        episode_id=EpisodeId("1004"),
        avid=BvId("BV1D84y1t76J"),
        cid=CId("456"),
        metadata=ItemMetaData(
            title="4 第四话",
            thumb="https://img/ep.jpg",
            premiered=1_700_000_000,
            duration=1200,
            dateadded=1_700_000_100,
        ),
    )
    media = BangumiSeason(
        season_id=SeasonId("99"),
        metadata=ItemMetaData(title="番剧", owner="UP", plot="简介", genre=["动画"]),
        items=[episode],
    )

    direct = project_media_items(
        BangumiEpisodeSource(id=episode.episode_id),
        media,
        _request(f"https://www.bilibili.com/bangumi/play/ep{episode.episode_id}"),
    )[0]
    season = project_media_items(
        BangumiSeasonSource(id=media.season_id),
        media,
        _request(f"https://www.bilibili.com/bangumi/play/ss{media.season_id}"),
    )[0]

    assert direct.planned_path == Path("4 第四话")
    assert season.planned_path == Path("番剧/4 第四话")
    assert season.url.endswith("ep1004")
    assert season.uploader == "UP"
    assert season.description == "简介"
    assert season.tags == ("动画",)


def test_bangumi_preview_prefixes_listing_without_mutating_metadata() -> None:
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

    item = project_media_items(
        BangumiSeasonSource(id=media.season_id),
        media,
        _request(f"https://www.bilibili.com/bangumi/play/ss{media.season_id}"),
    )[0]

    assert episode.metadata.title == "2 第二话"
    assert item.name == "【预告】2 第二话"
    assert item.planned_path == Path("番剧/【预告】2 第二话")


def test_cheese_projection_uses_original_episode_index_in_path_variables() -> None:
    episode = CheeseEpisode(
        index=7,
        episode_id=EpisodeId("7007"),
        avid=AId("123"),
        cid=CId("456"),
        metadata=ItemMetaData(title="第七节", premiered=1_700_000_000, dateadded=1_700_000_100),
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

    item = project_media_items(CheeseSeasonSource(id=media.season_id), media, request)[0]

    assert item.planned_path == Path("7-课程/第七节")
    assert item.url.endswith("ep7007")


def test_series_traversal_keeps_video_in_ancestry() -> None:
    video = UgcVideo(
        avid=BvId("BV1D84y1t76J"),
        metadata=ItemMetaData(title="投稿", owner="UP"),
        items=[UgcPage(page=2, cid=CId("456"), metadata=ItemMetaData(title="P2"))],
    )
    media = UgcSeries(
        series_id=SeriesId("99"),
        metadata=ItemMetaData(title="系列", owner="UP"),
        items=[video],
    )
    request = _request("https://space.bilibili.com/123/lists/99?type=series", episodes="1")

    ancestry, page = next(iter_media_items(media))
    listing = project_media_items(UgcVideoSource(id=video.avid), media, request)[0]

    assert ancestry[-1] is video
    assert page is video.items[0]
    assert listing.planned_path == Path("系列/投稿/P2")
    assert listing.url.endswith("?p=2")


def test_favourite_projection_uses_single_and_multi_page_layouts() -> None:
    single = UgcVideo(
        avid=BvId("BV1D84y1t76J"),
        metadata=ItemMetaData(title="单P", owner="视频UP"),
        items=[UgcPage(page=1, cid=CId("101"), metadata=ItemMetaData(title="P1"))],
    )
    multi = UgcVideo(
        avid=BvId("BV1D84y1t76K"),
        metadata=ItemMetaData(title="多P", owner="视频UP"),
        items=[
            UgcPage(page=1, cid=CId("201"), metadata=ItemMetaData(title="第一段")),
            UgcPage(page=2, cid=CId("202"), metadata=ItemMetaData(title="第二段")),
        ],
    )
    media = UgcFav(
        fid=FId("88"),
        metadata=ItemMetaData(title="收藏夹", owner="收藏者"),
        items=[single, multi],
    )
    request = _request("https://space.bilibili.com/123/favlist?fid=88", episodes="1~2")

    items = project_media_items(UgcVideoSource(id=single.avid), media, request)

    assert [item.planned_path for item in items] == [
        Path("收藏者的收藏夹/收藏夹/单P"),
        Path("收藏者的收藏夹/收藏夹/多P/第一段"),
        Path("收藏者的收藏夹/收藏夹/多P/第二段"),
    ]
    assert items[0].name == "单P"


def test_collection_projection_keeps_single_page_layout_and_expands_multi_page_video() -> None:
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
    media = UgcCollection(
        collection_id=CollectionId("66"),
        metadata=ItemMetaData(title="合集", owner="UP"),
        items=[single, multi],
    )
    request = _request("https://space.bilibili.com/123/lists/66?type=season", episodes="1~2")
    source = UgcCollectionSource(id=media.collection_id, owner_id=MId("123"))

    ancestry_and_items = list(iter_media_items(media))
    items = project_media_items(source, media, request)

    assert [item.planned_path for item in items] == [
        Path("合集/单P"),
        Path("合集/多P/第一段"),
        Path("合集/多P/第二段"),
    ]
    assert ancestry_and_items[1][0][-1] is multi
    assert ancestry_and_items[2][0][-1] is multi


def test_space_and_watch_later_projection_keep_their_nested_page_layouts() -> None:
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

    space_item = project_media_items(
        UgcSpaceSource(id=space.mid),
        space,
        _request("https://space.bilibili.com/123", episodes="1"),
    )[0]
    watch_later_item = project_media_items(
        UgcWatchLaterSource(id=AId("1")),
        watch_later,
        _request("https://www.bilibili.com/watchlater", episodes="1"),
    )[0]

    assert space_item.planned_path == Path("空间UP的全部投稿视频/投稿/P1")
    assert watch_later_item.planned_path == Path("稍后再看/投稿/P1")
