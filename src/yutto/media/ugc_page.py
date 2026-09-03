from __future__ import annotations

from dataclasses import dataclass

from yutto.media._abc import MediaItem


@dataclass(slots=True, kw_only=True)
class UgcPage(MediaItem):
    """UGC 投稿中的一个分 P。"""
