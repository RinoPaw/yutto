from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from yutto.downloader.downloaded import (
    Downloaded,
    DownloadedChapter,
    DownloadedDanmaku,
    DownloadedSubtitle,
    DownloadedSubtitleLine,
)
from yutto.media import MediaEntry, UgcPage, UgcVideo
from yutto.types import AId, CId
from yutto.utils.metadata import ChapterInfoData, ItemMetaData, write_metadata


def test_media_relation_owns_index_instead_of_leaf() -> None:
    aid = AId("123")
    page = UgcPage(aid=aid, cid=CId("456"), metadata=ItemMetaData(title="P3"))
    video = UgcVideo(
        aid=aid,
        page_count=3,
        metadata=ItemMetaData(title="投稿"),
        items=(MediaEntry(index=3, media=page),),
    )

    assert video.items[0].index == 3
    assert video.items[0].media is page
    assert not hasattr(page, "index")
    with pytest.raises(FrozenInstanceError):
        video.page_count = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        page.metadata.title = "changed"  # type: ignore[misc]


def test_downloaded_resources_are_deeply_immutable() -> None:
    line = DownloadedSubtitleLine(content="字幕", start=0, end=1)
    subtitle = DownloadedSubtitle(lang="zh-CN", lines=(line,))
    chapter = DownloadedChapter(start=0, end=1, content="章节")
    danmaku = DownloadedDanmaku(source_type="xml", save_type="xml", data=("<i />",))
    downloaded = Downloaded(
        subtitles=(subtitle,),
        danmaku=danmaku,
        chapters=(chapter,),
    )

    assert isinstance(downloaded.subtitles, tuple)
    assert isinstance(downloaded.subtitles[0].lines, tuple)
    assert isinstance(downloaded.danmaku.data, tuple)
    assert isinstance(downloaded.chapters, tuple)
    with pytest.raises(FrozenInstanceError):
        line.content = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        chapter.content = "changed"  # type: ignore[misc]


def test_chapters_are_explicit_writer_input_not_domain_metadata(tmp_path) -> None:
    metadata = ItemMetaData(title="测试")
    chapter = ChapterInfoData(start=0, end=10, content="开场")

    path = write_metadata(
        metadata,
        tmp_path / "video.mp4",
        {},
        chapter_info_data=(chapter,),
    )

    assert not hasattr(metadata, "chapter_info_data")
    content = path.read_text(encoding="utf-8")
    assert "chapter_info_data" in content
    assert "开场" in content
