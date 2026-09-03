from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yutto.types import BilibiliId
    from yutto.utils.metadata import ContainerMetaData, ItemMetaData, MetaData


@dataclass(slots=True, kw_only=True)
class Media(ABC):
    id: BilibiliId
    title: str
    extraMetaData: MetaData | None = None


@dataclass(slots=True, kw_only=True)
class MediaItem(Media):
    extraMetaData: ItemMetaData | None = None


@dataclass(slots=True, kw_only=True)
class MediaContainer(Media):
    extraMetaData: ContainerMetaData | None = None
    items: list[Media]
