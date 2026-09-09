from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from biliass import BlockOptions

from yutto.core.result import Artifact, ArtifactKind
from yutto.utils.danmaku import write_danmaku
from yutto.utils.metadata import write_chapter_info, write_metadata
from yutto.utils.subtitle import write_subtitle

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from yutto.downloader.planner import DownloadPlan
    from yutto.types import MultiLangSubtitle
    from yutto.utils.danmaku import DanmakuData, DanmakuOptions
    from yutto.utils.metadata import ChapterInfoData, ItemMetaData


@dataclass(frozen=True, slots=True)
class WrittenResource:
    kind: ArtifactKind
    paths: tuple[Path, ...]
    labels: tuple[str, ...] = ()

    @property
    def artifacts(self) -> tuple[Artifact, ...]:
        return tuple(Artifact(kind=self.kind, path=path) for path in self.paths)


class ArtifactWriter:
    """Write fetched resource bodies according to a DownloadPlan."""

    def write(
        self,
        metadata: ItemMetaData,
        plan: DownloadPlan,
        *,
        subtitles: tuple[MultiLangSubtitle, ...] = (),
        danmaku: DanmakuData | None = None,
        cover_data: bytes | None = None,
        chapter_info_data: tuple[ChapterInfoData, ...] = (),
    ) -> Iterator[WrittenResource]:
        resources = plan.resources

        if subtitles:
            paths = tuple(
                write_subtitle(subtitle["lines"], plan.paths.output, subtitle["lang"]) for subtitle in subtitles
            )
            yield WrittenResource(
                kind=ArtifactKind.SUBTITLE,
                paths=paths,
                labels=tuple(subtitle["lang"] for subtitle in subtitles),
            )

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
            path = write_metadata(
                metadata,
                plan.paths.output,
                {
                    "premiered": resources.metadata.premiered,
                    "dateadded": resources.metadata.dateadded,
                },
            )
            yield WrittenResource(kind=ArtifactKind.METADATA, paths=(path,))

        if cover_data is not None:
            plan.paths.cover.write_bytes(cover_data)
            if resources.save_cover:
                plan.paths.saved_cover.write_bytes(cover_data)
                yield WrittenResource(kind=ArtifactKind.COVER, paths=(plan.paths.saved_cover,))

        if chapter_info_data:
            write_chapter_info(
                plan.item,
                list(chapter_info_data),
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
