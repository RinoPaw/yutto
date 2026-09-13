from __future__ import annotations

import argparse

from yutto.cli.input import path_from_cli


def add_serve_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument(
        "--ffmpeg-path",
        help="FFmpeg 可执行文件路径，默认从 PATH 解析（`ffmpeg`）",
    )
    parser.add_argument("--host", help="监听地址（仅允许本机回环地址）")
    parser.add_argument("--port", type=int, help="监听端口，默认为 11223")
    parser.add_argument(
        "--allow-origin",
        action="append",
        help="允许访问的浏览器 Origin；可重复指定，默认拒绝所有浏览器 Origin",
    )
    parser.add_argument(
        "--token-file",
        type=path_from_cli,
        help="server token 文件；也可通过 YUTTO_SERVER_TOKEN 环境变量提供",
    )
    parser.add_argument(
        "--download-root",
        type=path_from_cli,
        help="RPC 下载目录的根目录，默认为配置中的下载目录",
    )
    parser.add_argument(
        "--tmp-root",
        type=path_from_cli,
        help="RPC 临时目录的根目录，默认与下载目录相同",
    )
    parser.add_argument(
        "--auth-file",
        type=path_from_cli,
        help="server 可读取的认证信息文件",
    )
    parser.add_argument(
        "--max-fetch-workers",
        type=int,
        help="单任务允许的最大解析并发数",
    )
    parser.add_argument(
        "--max-download-workers",
        type=int,
        help="单任务允许的最大下载并发数",
    )
    parser.add_argument("--task-limit", type=int, help="保留的任务及排队任务总数上限")
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        help="同时执行的下载任务数，默认为 1",
    )
