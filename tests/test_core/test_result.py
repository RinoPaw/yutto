from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import ValidationError

from yutto.core.result import (
    Artifact,
    ArtifactKind,
    DownloadResult,
    ItemResult,
    ItemSkipReason,
    ItemState,
    ResolveResult,
)
from yutto.media import MediaEntry, UgcPage, UgcVideo
from yutto.types import AId, CId
from yutto.utils.metadata import ItemMetaData

pytestmark = pytest.mark.processor


def test_result_models_are_frozen_and_reject_extra_fields():
    result = DownloadResult()

    with pytest.raises(ValidationError, match="frozen"):
        result.items = ()  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError, match="Extra inputs"):
        Artifact(kind=ArtifactKind.MEDIA, path=Path("video.mp4"), size=1)  # ty: ignore[unknown-argument]


def test_resolve_result_keeps_media_tree_without_flat_projection():
    aid = AId("808982399")
    page = UgcPage(
        aid=aid,
        cid=CId("10"),
        metadata=ItemMetaData(title="P2"),
    )
    entry = MediaEntry(index=2, media=page)
    video = UgcVideo(
        aid=aid,
        metadata=ItemMetaData(title="标题"),
        items=(entry,),
    )
    result = ResolveResult(items=(video,))

    assert result.items == (video,)
    root = result.items[0]
    assert isinstance(root, UgcVideo)
    assert root.items == (entry,)
    assert root.items[0].media is page
    assert root is video

    with pytest.raises(FrozenInstanceError):
        result.items = ()  # ty: ignore[invalid-assignment]


def test_item_result_output_path_only_describes_real_media_output():
    resource_only = ItemResult(state=ItemState.DONE)
    media_download = ItemResult(
        state=ItemState.DONE,
        output_path=Path("video.mp4"),
        artifacts=(Artifact(kind=ArtifactKind.MEDIA, path=Path("video.mp4")),),
    )
    existing_media = ItemResult(
        state=ItemState.SKIPPED,
        output_path=Path("video.mp4"),
        skip_reason=ItemSkipReason.ALREADY_EXISTS,
        artifacts=(Artifact(kind=ArtifactKind.MEDIA, path=Path("video.mp4")),),
    )
    missing_media = ItemResult(
        state=ItemState.SKIPPED,
        skip_reason=ItemSkipReason.NO_MEDIA_STREAM,
    )

    assert resource_only.output_path is None
    assert resource_only.has_downloaded_media is False
    assert media_download.has_downloaded_media is True
    assert existing_media.has_downloaded_media is False
    assert missing_media.output_path is None

    with pytest.raises(ValidationError, match="done item must not have"):
        ItemResult(
            state=ItemState.DONE,
            skip_reason=ItemSkipReason.ALREADY_EXISTS,
        )
    with pytest.raises(ValidationError, match="skipped item must have"):
        ItemResult(state=ItemState.SKIPPED)
    with pytest.raises(ValidationError, match="already-existing item must have"):
        ItemResult(state=ItemState.SKIPPED, skip_reason=ItemSkipReason.ALREADY_EXISTS)
    with pytest.raises(ValidationError, match="must not have an output path"):
        ItemResult(
            state=ItemState.SKIPPED,
            output_path=Path("video.mp4"),
            skip_reason=ItemSkipReason.NO_MEDIA_STREAM,
        )
