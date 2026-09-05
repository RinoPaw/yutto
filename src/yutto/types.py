from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple, TypedDict

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from pathlib import Path
    from typing import Any

    from yutto.core.result import ResolvedItem
    from yutto.stream import AudioCodec, AudioQuality, VideoCodec, VideoQuality
    from yutto.utils.danmaku import DanmakuData, DanmakuSaveType
    from yutto.utils.filter import PublicationTimeFilter
    from yutto.utils.metadata import ChapterInfoData, ItemMetaData
    from yutto.utils.subtitle import SubtitleData


@dataclass(slots=True)
class BilibiliId:
    """所有 bilibili id 的基类"""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError(f"无效的 bilibili ID：{self.value!r}")

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        return type(self) is type(other) and self.value == other.value

    def to_param(self) -> str:
        raise NotImplementedError("请不要直接使用 BilibiliId")


@dataclass(slots=True)
class AvId(BilibiliId):
    """AId 与 BvId 的统一，大多数 API 只需要其中一种即可正常工作

    ### Examples

    ``` python
    # 初始化
    # 这两个 Id 事实上是完全一样的，指向同一个资源
    # 因此我们只获取其一即可，在能够获取 BvId 的情况下建议使用 BvId
    aid = AId("808982399")
    bvid = BvId("BV1f34y1k7D5")

    # 使用
    # 由于 B 站大多数需要 aid/bvid 的接口都是只提供其一即可，
    # 因此我们可以直接这样通过格式化的方式来产生一个合法的接口链接
    api = "https://api.bilibili.com/x/player/pagelist?{aid}&{bvid}&jsonp=jsonp"

    # 为了方便，继承了 AvId 的 AId 和 BvId 都可以通过 to_param 方法简化这一步
    api = api.format(aid=aid.to_param(), bvid=bvid.to_param())
    # 这样就完全屏蔽了 aid 和 bvid 的差异了
    ```
    """

    def to_url(self) -> str:
        raise NotImplementedError("请不要直接使用 AvId")


@dataclass(slots=True)
class AId(AvId):
    """AID"""

    def __init__(self, aid: Any):
        self.value = str(aid)
        self.__post_init__()

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 AId：{self.value!r}")

    def to_url(self) -> str:
        return f"https://www.bilibili.com/video/av{self.value}"

    def to_param(self) -> str:
        return f"aid={self.value}"


@dataclass(slots=True)
class BvId(AvId):
    """BVID"""

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.startswith("BV") or not self.value[2:].isalnum():
            raise ValueError(f"无效的 BVID：{self.value!r}")

    def to_url(self) -> str:
        return f"https://www.bilibili.com/video/{self.value}"

    def to_param(self) -> str:
        return f"bvid={self.value}"


@dataclass(slots=True)
class CId(BilibiliId):
    """视频 ID"""

    def __init__(self, cid: Any):
        self.value = str(cid)
        self.__post_init__()

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 CId：{self.value!r}")

    def to_param(self) -> str:
        return f"cid={self.value}"


@dataclass(slots=True)
class EpisodeId(BilibiliId):
    """番剧/课程剧集 ID"""

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 EpisodeId：{self.value!r}")

    def to_param(self) -> str:
        return f"episode_id={self.value}"


@dataclass(slots=True)
class MediaId(BilibiliId):
    """番剧 ID"""

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 MediaId：{self.value!r}")

    def to_param(self) -> str:
        return f"media_id={self.value}"


@dataclass(slots=True)
class SeasonId(BilibiliId):
    """番剧/课程（季） ID"""

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 SeasonId：{self.value!r}")

    def to_param(self) -> str:
        return f"season_id={self.value}"


@dataclass(slots=True)
class MId(BilibiliId):
    """用户 ID"""

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 MId：{self.value!r}")

    def to_param(self) -> str:
        return f"mid={self.value}"


@dataclass(slots=True)
class FId(BilibiliId):
    """收藏夹 ID"""

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 FId：{self.value!r}")

    def to_param(self) -> str:
        return f"fid={self.value}"


@dataclass(slots=True)
class SeriesId(BilibiliId):
    """视频系列 ID"""

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 SeriesId：{self.value!r}")

    def to_param(self) -> str:
        return f"series_id={self.value}"


@dataclass(slots=True)
class CollectionId(BilibiliId):
    """UGC 视频合集 ID"""

    def __post_init__(self) -> None:
        if not self.value.isascii() or not self.value.isdigit():
            raise ValueError(f"无效的 CollectionId：{self.value!r}")

    def to_param(self) -> str:
        return f"season_id={self.value}"


def format_ids(*ids: BilibiliId) -> str:
    formatted_ids = [id_.to_param().replace("=", ": ", 1) for id_ in ids]
    return ", ".join(formatted_ids)


class VideoUrlMeta(TypedDict):
    url: str
    mirrors: list[str]
    codec: VideoCodec
    width: int
    height: int
    quality: VideoQuality


class AudioUrlMeta(TypedDict):
    url: str
    mirrors: list[str]
    codec: AudioCodec
    width: int
    height: int
    quality: AudioQuality


class MultiLangSubtitle(TypedDict):
    lang: str
    lines: SubtitleData


@dataclass(slots=True, kw_only=True)
class Options:
    pass


class ExtractorOptions(TypedDict):
    episodes: str
    with_extra_episodes: bool
    skip_preview: bool
    require_video: bool
    require_audio: bool
    require_danmaku: bool
    require_subtitle: bool
    require_metadata: bool
    require_cover: bool
    require_chapter_info: bool
    danmaku_format: DanmakuSaveType
    subpath_template: str
    ai_translation_language: str | None
    publication_time_filter: PublicationTimeFilter


class EpisodeInfo(TypedDict):
    """下载期条目信息：不可变 listing 快照与可调整的实际路径。"""

    listing: ResolvedItem
    path: Path  # 初始等于 listing.planned_path，下载时可能因去重而调整


class EpisodeData(TypedDict):
    """剧集数据 = canonical listing + 下载期路径 + 下载所需的资源数据。"""

    info: EpisodeInfo
    videos: list[VideoUrlMeta]
    audios: list[AudioUrlMeta]
    subtitles: list[MultiLangSubtitle]
    metadata: ItemMetaData | None
    danmaku: DanmakuData
    cover_data: bytes | None
    chapter_info_data: list[ChapterInfoData]


class ResolvableEpisode(NamedTuple):
    """listing 阶段产出的条目：info 立即可用，data 在下载前按需创建并解析"""

    info: EpisodeInfo
    resolve_data: Callable[[], Coroutine[Any, Any, EpisodeData | None]]


class FavouriteMetaData(TypedDict):
    fid: FId
    title: str


class FavouriteVideoData(TypedDict):
    """收藏夹条目的元数据，含完整视频标题与分 p 数量"""

    avid: AvId
    title: str  # B 站返回的视频标题（人工填写）
    page: int  # 视频分 p 数量


class UserInfo(TypedDict):
    vip_status: bool
    is_login: bool
