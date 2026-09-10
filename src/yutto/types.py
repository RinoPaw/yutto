from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, TypedDict

if TYPE_CHECKING:
    from typing import Self

    from yutto.media.codec import AudioCodec, VideoCodec
    from yutto.media.quality import AudioQuality, VideoQuality
    from yutto.utils.subtitle import SubtitleData


class BilibiliId(NamedTuple):
    """所有 bilibili id 的基类"""

    value: str

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BilibiliId):
            return False
        return self.value == other.value

    def to_param(self) -> str:
        raise NotImplementedError("请不要直接使用 BilibiliId")


class AvId(BilibiliId):
    """AId 与 BvId 的统一，大多数 API 只需要其中一种即可正常工作。"""

    XOR_CODE = 23442827791579
    MASK_CODE = 2251799813685247
    MAX_AID = 1 << 51
    ALPHABET = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"
    ENCODE_MAP = 8, 7, 0, 5, 1, 3, 2, 4, 6
    DECODE_MAP = tuple(reversed(ENCODE_MAP))

    BASE = len(ALPHABET)
    PREFIX = "BV1"
    PREFIX_LEN = len(PREFIX)
    CODE_LEN = len(ENCODE_MAP)

    @staticmethod
    def av2bv(aid: int) -> str:
        bvid = [""] * 9
        tmp = (AvId.MAX_AID | aid) ^ AvId.XOR_CODE
        for i in range(AvId.CODE_LEN):
            bvid[AvId.ENCODE_MAP[i]] = AvId.ALPHABET[tmp % AvId.BASE]
            tmp //= AvId.BASE
        return AvId.PREFIX + "".join(bvid)

    @staticmethod
    def bv2av(bvid: str) -> int:
        assert bvid[:3] == AvId.PREFIX

        bvid = bvid[3:]
        tmp = 0
        for i in range(AvId.CODE_LEN):
            idx = AvId.ALPHABET.index(bvid[AvId.DECODE_MAP[i]])
            tmp = tmp * AvId.BASE + idx
        return (tmp & AvId.MASK_CODE) ^ AvId.XOR_CODE

    def to_param(self) -> str:
        raise NotImplementedError("请不要直接使用 AvId")

    def to_url(self) -> str:
        raise NotImplementedError("请不要直接使用 AvId")

    def as_aid(self) -> AId:
        if isinstance(self, AId):
            return self
        return AId(str(self.bv2av(self.value)))

    def as_bvid(self) -> BvId:
        if isinstance(self, BvId):
            return self
        return BvId(self.av2bv(int(self.value)))


class AId(AvId):
    """AID"""

    def __new__(cls, aid: object) -> Self:
        return super().__new__(cls, str(aid))

    def to_param(self) -> str:
        return f"aid={self.value}"

    def to_url(self) -> str:
        return f"https://www.bilibili.com/video/av{self.value}"


class BvId(AvId):
    """BVID"""

    def to_param(self) -> str:
        return f"bvid={self.value}"

    def to_url(self) -> str:
        return f"https://www.bilibili.com/video/{self.value}"


class CId(BilibiliId):
    """视频 ID"""

    def __new__(cls, cid: object) -> Self:
        return super().__new__(cls, str(cid))

    def to_param(self) -> str:
        return f"cid={self.value}"


class EpisodeId(BilibiliId):
    """番剧剧集 ID"""

    def to_param(self) -> str:
        return f"ep_id={self.value}"


class MediaId(BilibiliId):
    """番剧 ID"""

    def to_param(self) -> str:
        return f"media_id={self.value}"


class SeasonId(BilibiliId):
    """番剧（季） ID"""

    def to_param(self) -> str:
        return f"season_id={self.value}"


class MId(BilibiliId):
    """用户 ID"""

    def to_param(self) -> str:
        return f"mid={self.value}"


class FId(BilibiliId):
    """收藏夹 ID"""

    def to_param(self) -> str:
        return f"fid={self.value}"


class SeriesId(BilibiliId):
    """视频系列 ID"""

    def to_param(self) -> str:
        return f"series_id={self.value}"


class CollectionId(BilibiliId):
    """UGC 视频合集 ID"""

    def to_param(self) -> str:
        return f"season_id={self.value}"


def format_ids(*id: BilibiliId) -> str:
    return ", ".join(item.to_param().replace("=", ": ", 1) for item in id)


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


class FavouriteMetaData(TypedDict):
    fid: FId
    title: str


class FavouriteVideoData(TypedDict):
    """收藏夹条目的元数据，含完整视频标题与分 p 数量"""

    avid: AvId
    title: str
    page: int


class UserInfo(TypedDict):
    vip_status: bool
    is_login: bool


if __name__ == "__main__":
    aid = AId("add")
    cid = CId("xxx")
    print(f"?{aid.to_param()}&{cid.to_param()}")
