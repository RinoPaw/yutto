from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

from yutto.cli.compat import DeprecatedExtraEpisodesAction
from yutto.cli.input import alias_parser, path_from_cli
from yutto.cli.settings import YuttoSettings
from yutto.stream import audio_quality_priority_default, video_quality_priority_default
from yutto.utils.functional.functional import map_optional

if TYPE_CHECKING:
    from collections.abc import Sequence


DownloadResourceType: TypeAlias = Literal[
    "video",
    "audio",
    "subtitle",
    "metadata",
    "danmaku",
    "cover",
    "chapter_info",
]
DOWNLOAD_RESOURCE_TYPES: tuple[DownloadResourceType, ...] = (
    "video",
    "audio",
    "subtitle",
    "metadata",
    "danmaku",
    "cover",
    "chapter_info",
)


def add_download_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.add_argument(
        "source",
        metavar="url",
        help="视频主页 URL、Bilibili ID 或 url 列表（需使用 file scheme）",
    )
    _add_basic_arguments(parser, settings)
    _add_auth_arguments(parser, settings)
    _add_selection_arguments(parser)
    _add_resource_arguments(parser, settings)
    _add_danmaku_arguments(parser, settings)
    _add_batch_arguments(parser, settings)

    batch_file = parser.add_argument_group("batch file", "批量下载文件参数")
    batch_file.add_argument("--no-inherit", action="store_true", help="不继承父级参数")

    config = parser.add_argument_group("config", "配置文件参数")
    config.add_argument("--config", help="配置文件路径")


def _add_basic_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    group = parser.add_argument_group("basic", "基础参数")
    group.add_argument(
        "-n",
        "--num-workers",
        dest="download_workers",
        type=int,
        default=settings.basic.num_workers,
        help="同时用于下载的最大 Worker 数",
    )
    group.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=settings.basic.jobs,
        help="同时下载的视频数量，默认为 1",
    )
    group.add_argument(
        "--fetch-workers",
        type=int,
        default=settings.basic.fetch_workers,
        help="批量解析时同时请求的最大 Worker 数",
    )
    group.add_argument(
        "-q",
        "--video-quality",
        default=settings.basic.video_quality,
        choices=video_quality_priority_default,
        type=int,
        help="视频清晰度等级（127:8K, 126:Dolby Vision, 125:4K·HDR10, 120:4K, 116:1080P60, 112:1080P+, 100:智能修复, 80:1080P, 74:720P60, 64:720P, 32:480P, 16:360P）",
    )
    group.add_argument(
        "-aq",
        "--audio-quality",
        default=settings.basic.audio_quality,
        choices=audio_quality_priority_default,
        type=int,
        help="音频码率等级（30251:Hi-Res, 30255:Dolby Audio, 30250:Dolby Atmos, 30280:320kbps, 30232:128kbps, 30216:64kbps）",
    )
    group.add_argument(
        "--vcodec",
        default=settings.basic.vcodec,
        metavar="DOWNLOAD_VCODEC:SAVE_VCODEC",
        help="视频编码格式（<下载格式>:<生成格式>）",
    )
    group.add_argument(
        "--acodec",
        default=settings.basic.acodec,
        metavar="DOWNLOAD_ACODEC:SAVE_ACODEC",
        help="音频编码格式（<下载格式>:<生成格式>）",
    )
    group.add_argument(
        "--download-vcodec-priority",
        default=settings.basic.download_vcodec_priority,
        type=lambda codecs: codecs.split(",") if codecs != "auto" else None,
        help="视频编码格式优先级，使用 `,` 分隔，如 `hevc,avc,av1`，默认为 `auto`，即根据 vcodec 中「下载编码」自动推断",
    )
    group.add_argument(
        "--output-format",
        default=settings.basic.output_format,
        choices=["infer", "mp4", "mkv", "mov"],
        help="输出格式（infer 为自动推断）",
    )
    group.add_argument(
        "--output-format-audio-only",
        default=settings.basic.output_format_audio_only,
        choices=["infer", "m4a", "aac", "mp3", "flac", "mp4", "mkv", "mov"],
        help="仅包含音频流时所使用的输出格式（infer 为自动推断）",
    )
    group.add_argument(
        "--ffmpeg-path",
        default="ffmpeg",
        help="FFmpeg 可执行文件路径，默认从 PATH 解析（`ffmpeg`）",
    )
    group.add_argument(
        "--ai-translation-language",
        default=settings.basic.ai_translation_language,
        help="启用 AI 原声翻译功能，并指定翻译目标语言（如 en 等）",
    )
    group.add_argument(
        "-df",
        "--danmaku-format",
        default=settings.basic.danmaku_format,
        choices=["xml", "ass", "protobuf"],
        help="弹幕类型",
    )
    group.add_argument(
        "-bs",
        "--block-size",
        default=settings.basic.block_size,
        type=float,
        help="分块下载时各块大小，单位为 MiB，默认为 0.5MiB",
    )
    group.add_argument(
        "-w",
        "--overwrite",
        default=settings.basic.overwrite,
        action="store_true",
        help="强制覆盖已下载内容",
    )
    group.add_argument(
        "-x",
        "--proxy",
        default=settings.basic.proxy,
        help="设置代理（auto 为系统代理、no 为不使用代理、当然也可以设置代理值）",
    )
    group.add_argument(
        "-d",
        "--dir",
        default=path_from_cli(settings.basic.dir),
        type=path_from_cli,
        help="下载目录，默认为运行目录",
    )
    group.add_argument(
        "--tmp-dir",
        default=map_optional(path_from_cli, settings.basic.tmp_dir),
        type=path_from_cli,
        help="用来存放下载过程中临时文件的目录，默认为下载目录",
    )
    group.add_argument(
        "-c",
        "--sessdata",
        default=settings.basic.sessdata,
        help="（弃用）Cookies 中的 SESSDATA 字段，推荐改用 --auth",
    )
    group.add_argument(
        "-tp",
        "--subpath-template",
        default=settings.basic.subpath_template,
        help="多级目录的存储路径模板",
    )
    group.add_argument(
        "-af",
        "--alias-file",
        dest="aliases",
        type=alias_parser,
        default=settings.basic.aliases,
        help="设置 url 别名文件路径",
    )
    group.add_argument(
        "--metadata-format-premiered",
        dest="metadata_premiered_format",
        default=settings.basic.metadata_format_premiered,
        help="专用于 metadata 文件中 premiered 字段的日期格式",
    )
    group.add_argument(
        "--download-interval",
        default=settings.basic.download_interval,
        type=int,
        help="设置下载间隔，单位为秒",
    )
    group.add_argument(
        "--banned-mirrors-pattern",
        default=settings.basic.banned_mirrors_pattern,
        help="禁用下载链接的镜像源，使用正则匹配",
    )
    group.add_argument(
        "--vip-strict",
        default=settings.basic.vip_strict,
        action="store_true",
        help="启用严格检查大会员生效",
    )
    group.add_argument(
        "--login-strict",
        default=settings.basic.login_strict,
        action="store_true",
        help="启用严格检查登录状态",
    )
    group.add_argument(
        "--no-color",
        default=settings.basic.no_color,
        action="store_true",
        help="不使用颜色",
    )
    group.add_argument(
        "--no-progress",
        default=settings.basic.no_progress,
        action="store_true",
        help="不显示进度条",
    )
    group.add_argument(
        "--debug",
        default=settings.basic.debug,
        action="store_true",
        help="启用 debug 模式",
    )


def _add_auth_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    group = parser.add_argument_group("auth", "个人信息认证参数")
    group.add_argument(
        "--auth",
        default=settings.auth.auth,
        help="登录 Cookie，格式如 `SESSDATA=xxxxx; bili_jct=yyyyy`",
    )
    group.add_argument(
        "--auth-file",
        default=map_optional(path_from_cli, settings.auth.auth_file),
        type=path_from_cli,
        help="认证信息文件路径",
    )
    group.add_argument(
        "--auth-profile",
        default=settings.auth.auth_profile,
        help="认证信息 profile 名称，默认 default",
    )


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("selection", "内容选择参数")
    group.add_argument(
        "-p",
        "--episodes",
        dest="selection_expr",
        default=None,
        help="选择当前资源对应列表中的条目；未指定时使用该资源的默认选择",
    )


def _add_resource_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    group = parser.add_argument_group("resource", "资源选择参数")
    group.add_argument(
        "--video-only",
        dest="require_audio",
        action=_create_resource_action(deselect=["audio"]),
        help="仅下载视频流",
    )
    group.add_argument(
        "--audio-only",
        dest="require_video",
        action=_create_resource_action(deselect=["video"]),
        help="仅下载音频流",
    )
    group.add_argument(
        "--no-danmaku",
        dest="require_danmaku",
        action=_create_resource_action(deselect=["danmaku"]),
        help="不生成弹幕文件",
    )
    group.add_argument(
        "--danmaku-only",
        dest="require_danmaku",
        action=_create_resource_action(select=["danmaku"], deselect=_invert_resources(["danmaku"])),
        help="仅生成弹幕文件",
    )
    group.add_argument(
        "--no-subtitle",
        dest="require_subtitle",
        action=_create_resource_action(deselect=["subtitle"]),
        help="不生成字幕文件",
    )
    group.add_argument(
        "--subtitle-only",
        dest="require_subtitle",
        action=_create_resource_action(select=["subtitle"], deselect=_invert_resources(["subtitle"])),
        help="仅生成字幕文件",
    )
    group.add_argument(
        "--with-metadata",
        dest="require_metadata",
        action=_create_resource_action(select=["metadata"]),
        help="生成元数据文件",
    )
    group.add_argument(
        "--metadata-only",
        dest="require_metadata",
        action=_create_resource_action(select=["metadata"], deselect=_invert_resources(["metadata"])),
        help="仅生成元数据文件",
    )
    group.add_argument(
        "--no-cover",
        dest="require_cover",
        action=_create_resource_action(deselect=["cover"]),
        help="不生成封面",
    )
    group.add_argument(
        "--cover-only",
        dest="require_cover",
        action=_create_resource_action(select=["cover"], deselect=_invert_resources(["cover"])),
        help="仅生成封面",
    )
    group.add_argument(
        "--no-chapter-info",
        dest="require_chapter_info",
        action=_create_resource_action(deselect=["chapter_info"]),
        help="不封装章节信息",
    )
    group.add_argument(
        "--save-cover",
        default=settings.resource.save_cover,
        action="store_true",
        help="生成视频流封面后单独保存封面文件",
    )
    group.set_defaults(
        require_video=settings.resource.require_video,
        require_audio=settings.resource.require_audio,
        require_danmaku=settings.resource.require_danmaku,
        require_subtitle=settings.resource.require_subtitle,
        require_metadata=settings.resource.require_metadata,
        require_cover=settings.resource.require_cover,
        require_chapter_info=settings.resource.require_chapter_info,
    )


def _add_danmaku_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    group = parser.add_argument_group("danmaku", "弹幕设置参数")
    group.add_argument(
        "--danmaku-font-size",
        type=int,
        default=settings.danmaku.font_size,
        help="弹幕字体大小",
    )
    group.add_argument("--danmaku-font", default=settings.danmaku.font, help="弹幕字体")
    group.add_argument(
        "--danmaku-opacity",
        type=float,
        default=settings.danmaku.opacity,
        help="弹幕不透明度",
    )
    group.add_argument(
        "--danmaku-display-region-ratio",
        type=float,
        default=settings.danmaku.display_region_ratio,
        help="弹幕显示区域与视频高度的比例",
    )
    group.add_argument(
        "--danmaku-speed",
        type=float,
        default=settings.danmaku.speed,
        help="弹幕速度",
    )
    group.add_argument(
        "--danmaku-block-top",
        action="store_true",
        default=settings.danmaku.block_top,
        help="屏蔽顶部弹幕",
    )
    group.add_argument(
        "--danmaku-block-bottom",
        action="store_true",
        default=settings.danmaku.block_bottom,
        help="屏蔽底部弹幕",
    )
    group.add_argument(
        "--danmaku-block-scroll",
        action="store_true",
        default=settings.danmaku.block_scroll,
        help="屏蔽滚动弹幕",
    )
    group.add_argument(
        "--danmaku-block-reverse",
        action="store_true",
        default=settings.danmaku.block_reverse,
        help="屏蔽逆向弹幕",
    )
    group.add_argument(
        "--danmaku-block-fixed",
        action="store_true",
        default=settings.danmaku.block_fixed,
        help="屏蔽固定弹幕（顶部、底部）",
    )
    group.add_argument(
        "--danmaku-block-special",
        action="store_true",
        default=settings.danmaku.block_special,
        help="屏蔽高级弹幕",
    )
    group.add_argument(
        "--danmaku-block-colorful",
        action="store_true",
        default=settings.danmaku.block_colorful,
        help="屏蔽彩色弹幕",
    )
    group.add_argument(
        "--danmaku-block-keyword-patterns",
        default=settings.danmaku.block_keyword_patterns,
        type=lambda patterns: [pattern.strip() for pattern in patterns.split(",")],
        help="屏蔽匹配关键词的弹幕，使用逗号分隔",
    )


def _add_batch_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    group = parser.add_argument_group("batch", "批量下载参数")
    group.add_argument("-b", "--batch", action="store_true", help="批量下载")
    group.add_argument(
        "--with-extra-episodes",
        action="store_true",
        default=settings.batch.with_extra_episodes,
        help="同时下载附加剧集（PV、预告以及特别篇等专区内容）",
    )
    group.add_argument(
        "-s",
        "--with-section",
        dest="with_extra_episodes",
        action=DeprecatedExtraEpisodesAction,
        default=argparse.SUPPRESS,
        help="（弃用）等同于 --with-extra-episodes，请迁移到正式名称",
    )
    group.add_argument(
        "--skip-preview",
        action="store_true",
        default=settings.batch.skip_preview,
        help="跳过预告片",
    )
    group.add_argument(
        "--batch-filter-start-time",
        dest="publication_start_time",
        default=settings.batch.batch_filter_start_time,
        help="只下载该时间之后（包含临界值）发布的稿件",
    )
    group.add_argument(
        "--batch-filter-end-time",
        dest="publication_end_time",
        default=settings.batch.batch_filter_end_time,
        help="只下载该时间之前（不包含临界值）发布的稿件",
    )


def _create_resource_action(
    select: list[DownloadResourceType] | None = None,
    deselect: list[DownloadResourceType] | None = None,
):
    selected_items = select or []
    deselected_items = deselect or []

    class SelectRequiredAction(argparse.Action):
        def __init__(
            self,
            option_strings: Sequence[str],
            dest: str,
            nargs: int | str | None = None,
            **kwargs: Any,
        ):
            if nargs is not None:
                raise ValueError("nargs not allowed")
            super().__init__(option_strings, dest, nargs=0, **kwargs)

        def __call__(
            self,
            parser: argparse.ArgumentParser,
            namespace: argparse.Namespace,
            values: str | Sequence[str] | None,
            option_string: str | None = None,
        ) -> None:
            for item in selected_items:
                setattr(namespace, f"require_{item}", True)
            for item in deselected_items:
                setattr(namespace, f"require_{item}", False)

    return SelectRequiredAction


def _invert_resources(select: list[DownloadResourceType]) -> list[DownloadResourceType]:
    return [resource_type for resource_type in DOWNLOAD_RESOURCE_TYPES if resource_type not in select]
