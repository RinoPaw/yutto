from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any, TypedDict

from dict2xml import dict2xml

from yutto.utils.time import get_time_str_by_stamp

if TYPE_CHECKING:
    from pathlib import Path

    from yutto.types import MId


class Actor(TypedDict):
    name: str
    role: str
    thumb: str
    profile: str
    order: int


class ChapterInfoData(TypedDict):
    start: int
    end: int
    content: str


@dataclass(slots=True, kw_only=True)
class ItemMetaData:
    title: str = ""
    plot: str = ""
    premiered: int = 0
    duration: int = 0
    mid: MId | None = None
    owner: str = ""
    thumb: str = ""
    show_title: str = ""

    genre: list[str] = field(default_factory=list)
    tag: list[str] = field(default_factory=list)
    actors: list[Actor] = field(default_factory=list)

    dateadded: int = 0
    source: str = ""
    original_filename: str = ""
    website: str = ""
    chapter_info_data: list[ChapterInfoData] = field(default_factory=list)


def _metadata_as_dict(metadata: ItemMetaData) -> dict[str, Any]:
    return {field_.name: getattr(metadata, field_.name) for field_ in fields(metadata)}


def metadata_value_format(metadata: ItemMetaData, metadata_format: dict[str, str]) -> dict[str, Any]:
    formatted_metadata = _metadata_as_dict(metadata)
    for key, value in formatted_metadata.items():
        if key in metadata_format:
            assert isinstance(value, int)
            formatted_metadata[key] = get_time_str_by_stamp(value, metadata_format[key])
    return formatted_metadata


def write_metadata(metadata: ItemMetaData, video_path: Path, metadata_format: dict[str, str]) -> Path:
    metadata_path = video_path.with_suffix(".nfo")
    custom_root = "episodedetails"  # TODO: 不同视频类型使用不同的 root name
    # 增加字段格式化内容，后续如果需要调整可以继续调整
    user_formatted_metadata = (
        metadata_value_format(metadata, metadata_format) if metadata_format else _metadata_as_dict(metadata)
    )
    xml_content = dict2xml(user_formatted_metadata, wrap=custom_root, indent="  ")
    with metadata_path.open("w", encoding="utf-8") as f:
        f.write(xml_content)
    return metadata_path


def attach_chapter_info(metadata: ItemMetaData, chapter_info_data: list[ChapterInfoData]):
    metadata.chapter_info_data = chapter_info_data


# https://wklchris.github.io/blog/FFmpeg/FFmpeg.html#id26
def write_chapter_info(title: str, chapter_info_data: list[ChapterInfoData], chapter_path: Path):
    with chapter_path.open("w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        f.write(f"title={title}\n")
        for chapter in chapter_info_data:
            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1\n")
            f.write(f"START={chapter['start']}\n")
            f.write(f"END={chapter['end']}\n")
            f.write(f"title={chapter['content']}\n")
