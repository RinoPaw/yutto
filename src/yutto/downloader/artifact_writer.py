from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from biliass import BlockOptions

from yutto.core.result import Artifact, ArtifactKind
from yutto.utils.danmaku import write_danmaku
from yutto.utils.metadata import write_chapter_info, write_metadata
from yutto.utils.subtitle import write_subtitle

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from yutto.downloader.downloaded import Downloaded
    from yutto.downloader.planner import DownloadPlan
    from yutto.utils.danmaku import DanmakuOptions
    from yutto.utils.metadata import ItemMetaData


@dataclass(frozen=True, slots=True)
class WrittenResource:
    kind: ArtifactKind
    paths: tuple[Path, ...]
    labels: tuple[str, ...] = ()

    @property
    def artifacts(self) -> tuple[Artifact, ...]:
        return tuple(Artifact(kind=self.kind, path=path) for path in self.paths)


class ArtifactWriter:
    """Write already-downloaded resources according to a DownloadPlan."""

    def write(
        self,
        metadata: ItemMetaData,
        plan: DownloadPlan,
        downloaded: Downloaded,
    ) -> Iterator[WrittenResource]:
        resources = plan.resources

        if downloaded.subtitles:
            paths = tuple(
                write_subtitle(subtitle["lines"], plan.paths.output, subtitle["lang"])
                for subtitle in downloaded.subtitles
            )
            yield WrittenResource(
                kind=ArtifactKind.SUBTITLE,
                paths=paths,
                labels=tuple(subtitle["lang"] for subtitle in downloaded.subtitles),
            )

        danmaku = downloaded.danmaku
        if danmaku is not None and danmaku["data"]:
            paths = tuple(
                write_danmaku(
                    danmaku,
                    plan.paths.output,
                    resources.danmaku_height,
                    resources.danmaku_width,
                    create_danmaku_options(plan),
                )
            )
            yield WrittenResource(
                kind=ArtifactKind.DANMAKU,
                paths=paths,
                labels=(str(danmaku["save_type"]),),
            )

        if resources.has_metadata:
            metadata_for_write = (
                replace(metadata, chapter_info_data=list(downloaded.chapter_info_data))
                if downloaded.chapter_info_data
                else metadata
            )
            path = write_metadata(
                metadata_for_write,
                plan.paths.output,
                {
                    "premiered": resources.metadata.premiered,
                    "dateadded": resources.metadata.dateadded,
                },
            )
            yield WrittenResource(kind=ArtifactKind.METADATA, paths=(path,))

        if downloaded.cover_path is not None and resources.save_cover:
            shutil.copyfile(downloaded.cover_path, plan.paths.saved_cover)
            yield WrittenResource(kind=ArtifactKind.COVER, paths=(plan.paths.saved_cover,))

        if downloaded.chapter_info_data:
            write_chapter_info(
                plan.item,
                list(downloaded.chapter_info_data),
                plan.paths.chapter_info,
            )

    def cleanup_temporary(self, plan: DownloadPlan) -> None:
        plan.paths.chapter_info.unlink(missing_ok=True)
        plan.paths.cover.unlink(missing_ok=True)


def create_danmaku_options(plan: DownloadPlan) -> DanmakuOptions:
    options = plan.resources.danmaku
    return {
        "font_size": options.font_size,
        "font": options.font,
        "opacity": options.opacity,
        "display_region_ratio": options.display_region_ratio,
        "speed": options.speed,
        "block_options": BlockOptions(
            block_top=options.block_top,
            block_bottom=options.block_bottom,
            block_scroll=options.block_scroll,
            block_reverse=options.block_reverse,
            block_special=options.block_special,
            block_colorful=options.block_colorful,
            block_keyword_patterns=list(options.block_keyword_patterns),
        ),
    }
