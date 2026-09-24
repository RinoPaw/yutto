from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from yutto.core.result import ResolveResult
from yutto.media import MediaEntry, UgcFav, UgcPage, UgcVideo
from yutto.runtime import TaskSnapshot, TaskState
from yutto.scope import ROOT_SCOPE, Scope
from yutto.server.service import snapshot_to_json
from yutto.types import AId, CId, FId
from yutto.utils.metadata import ItemMetaData

pytestmark = pytest.mark.processor


def test_resolve_wire_keeps_relation_display_title_separate_from_media_title() -> None:
    aid = AId("808982399")
    video = UgcVideo(
        aid=aid,
        metadata=ItemMetaData(title="原始投稿标题"),
        items=(
            MediaEntry(
                index=1,
                media=UgcPage(
                    aid=aid,
                    cid=CId("10"),
                    metadata=ItemMetaData(title="P1"),
                ),
            ),
        ),
    )
    favourite = UgcFav(
        fid=FId("42"),
        metadata=ItemMetaData(title="收藏夹"),
        items=(MediaEntry(index=3, media=video, display_title="收藏时标题"),),
    )
    now = datetime(2026, 9, 24, tzinfo=UTC)
    snapshot = TaskSnapshot[Scope, ResolveResult](
        task_id="resolve-relation",
        state=TaskState.COMPLETED,
        payload=Scope({"source.value": "fid:42"}, parent=ROOT_SCOPE),
        result=ResolveResult(items=(favourite,)),
        error=None,
        created_at=now,
        started_at=now,
        finished_at=now,
        last_event_seq=1,
    )

    result = cast("dict[str, object]", snapshot_to_json(snapshot)["result"])
    favourite_wire = cast("list[dict[str, object]]", result["items"])[0]
    video_wire = cast("list[dict[str, object]]", favourite_wire["items"])[0]
    metadata = cast("dict[str, object]", video_wire["metadata"])

    assert video_wire["index"] == 3
    assert video_wire["display_title"] == "收藏时标题"
    assert metadata["title"] == "原始投稿标题"
