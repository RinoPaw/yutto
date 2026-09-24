from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, TypedDict

from dict2xml import dict2xml

from yutto.utils.time import get_time_str_by_stamp

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from yutto.types import MId


@dataclass(frozen=True, slots=True)
class Actor:
    name: str
    role: str
    thumb: str
    profile: str
    order: int

    def __getitem__(self, key: str) -> str | int:
        return getattr(self, key)


class ChapterInfoData(TypedDict):
    start: int
    end: int
    content: str


class MetaData(TypedDict):
    title: str
    show_title: str
    plot: str
    thumb: str
    premiered: int
    dateadded: int
    actor: list[dict[str, object]]
    genre: list[str]
    tag: list[str]
    source: str
    original_filename: str
    website: str
    chapter_info_data: list[ChapterInfoData]


@dataclass(frozen=True, slots=True, kw_only=True)
class ItemMetaData:
    title: str = ""
    plot: str = ""
    published_at: int = 0
    duration: int = 0
    mid: MId | None = None
    owner: str = ""
    thumb: str = ""
    show_title: str = ""

    genre: Sequence[str] = ()
    tag: Sequence[str] = ()
    actors: Sequence[Actor] = ()

    added_at: int = 0
    source: str = ""
    original_filename: str = ""
    website: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "genre", tuple(self.genre))
        object.__setattr__(self, "tag", tuple(self.tag))
        object.__setattr__(self, "actors", tuple(self.actors))


def _metadata_as_dict(
    metadata: MetaData | ItemMetaData,
    chapter_info_data: Sequence[ChapterInfoData] = (),
) -> dict[str, Any]:
    if isinstance(metadata, ItemMetaData):
        return {
            "title": metadata.title,
            "show_title": metadata.show_title,
            "plot": metadata.plot,
            "thumb": metadata.thumb,
            "premiered": metadata.published_at,
            "dateadded": metadata.added_at,
            "actor": [asdict(actor) for actor in metadata.actors],
            "genre": list(metadata.genre),
            "tag": list(metadata.tag),
            "source": metadata.source,
            "original_filename": metadata.original_filename,
            "website": metadata.website,
            "chapter_info_data": list(chapter_info_data),
        }
    result = dict(metadata)
    if chapter_info_data:
        result["chapter_info_data"] = list(chapter_info_data)
    return result


def metadata_value_format(
    metadata: MetaData | ItemMetaData,
    metadata_format: dict[str, str],
    chapter_info_data: Sequence[ChapterInfoData] = (),
) -> dict[str, Any]:
    formatted_metadata = _metadata_as_dict(metadata, chapter_info_data)
    for key, value in formatted_metadata.items():
        if key in metadata_format:
            assert isinstance(value, int)
            formatted_metadata[key] = get_time_str_by_stamp(value, metadata_format[key])
    return formatted_metadata


def write_metadata(
    metadata: MetaData | ItemMetaData,
    video_path: Path,
    metadata_format: dict[str, str],
    *,
    chapter_info_data: Sequence[ChapterInfoData] = (),
) -> Path:
    metadata_path = video_path.with_suffix(".nfo")
    custom_root = "episodedetails"  # TODO: 不同视频类型使用不同的 root name
    user_formatted_metadata = (
        metadata_value_format(metadata, metadata_format, chapter_info_data)
        if metadata_format
        else _metadata_as_dict(metadata, chapter_info_data)
    )
    xml_content = dict2xml(user_formatted_metadata, wrap=custom_root, indent="  ")
    with metadata_path.open("w", encoding="utf-8") as f:
        f.write(xml_content)
    return metadata_path


# https://wklchris.github.io/blog/FFmpeg/FFmpeg.html#id26
def write_chapter_info(title: str, chapter_info_data: Sequence[ChapterInfoData], chapter_path: Path):
    with chapter_path.open("w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        f.write(f"title={title}\n")
        for chapter in chapter_info_data:
            f.write("[CHAPTER]\n")
            f.write("TIMEBASE=1/1\n")
            f.write(f"START={chapter['start']}\n")
            f.write(f"END={chapter['end']}\n")
            f.write(f"title={chapter['content']}\n")
