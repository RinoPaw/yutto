from __future__ import annotations

import argparse

from yutto.cli.input import path_from_cli
from yutto.cli.settings import YuttoSettings
from yutto.utils.functional.functional import map_optional


def add_login_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.add_argument(
        "--mode",
        default="terminal",
        choices=["terminal", "web"],
        help="二维码展示方式：terminal 在终端展示，web 调起系统图片预览",
    )
    parser.add_argument(
        "--poll-interval",
        default=2.0,
        type=float,
        help="登录轮询间隔，单位：秒",
    )
    parser.add_argument(
        "--timeout",
        default=180,
        type=int,
        help="扫码登录超时时间，单位：秒",
    )
    add_auth_resolution_arguments(parser, settings)


def add_auth_subcommands(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.add_argument("--config", help="配置文件路径")
    subparsers = parser.add_subparsers(dest="auth_command", help="auth 子命令")
    subparsers.required = True

    login_parser = subparsers.add_parser("login", help="扫码登录并写入认证信息")
    add_login_arguments(login_parser, settings)

    status_parser = subparsers.add_parser("status", help="检查当前认证信息对应的登录状态")
    add_auth_status_arguments(status_parser, settings)

    logout_parser = subparsers.add_parser("logout", help="删除当前 profile 对应的认证信息")
    add_auth_logout_arguments(logout_parser, settings)


def add_auth_status_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.add_argument(
        "--auth",
        default=settings.auth.auth,
        help="登录 Cookie，格式如 `SESSDATA=xxxxx; bili_jct=yyyyy`",
    )
    add_auth_resolution_arguments(parser, settings)


def add_auth_logout_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.add_argument("--auth", default=settings.auth.auth, help=argparse.SUPPRESS)
    add_auth_storage_arguments(parser, settings)


def add_auth_resolution_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    add_auth_network_arguments(parser, settings)
    add_auth_storage_arguments(parser, settings)


def add_auth_network_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.add_argument(
        "-x",
        "--proxy",
        default=settings.basic.proxy,
        help="设置代理（auto 为系统代理、no 为不使用代理、当然也可以设置代理值）",
    )


def add_auth_storage_arguments(parser: argparse.ArgumentParser, settings: YuttoSettings) -> None:
    parser.add_argument(
        "--auth-file",
        default=map_optional(path_from_cli, settings.auth.auth_file),
        type=path_from_cli,
        help="认证信息文件路径",
    )
    parser.add_argument(
        "--auth-profile",
        default=settings.auth.auth_profile,
        help="认证信息 profile 名称，默认 default",
    )
    parser.add_argument("--config", help="配置文件路径")
