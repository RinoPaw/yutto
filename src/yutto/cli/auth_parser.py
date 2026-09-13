from __future__ import annotations

import argparse

from yutto.cli.input import path_from_cli


def add_auth_subcommands(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="配置文件路径")
    subparsers = parser.add_subparsers(dest="auth_command", help="auth 子命令", required=True)

    login_parser = subparsers.add_parser(
        "login",
        help="扫码登录并写入认证信息",
        argument_default=argparse.SUPPRESS,
    )
    _add_login_arguments(login_parser)

    status_parser = subparsers.add_parser(
        "status",
        help="检查当前认证信息对应的登录状态",
        argument_default=argparse.SUPPRESS,
    )
    _add_status_arguments(status_parser)

    logout_parser = subparsers.add_parser(
        "logout",
        help="删除当前 profile 对应的认证信息",
        argument_default=argparse.SUPPRESS,
    )
    _add_logout_arguments(logout_parser)


def _add_login_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mode",
        choices=["terminal", "web"],
        help="二维码展示方式：terminal 在终端展示，web 调起系统图片预览",
    )
    parser.add_argument("--poll-interval", type=float, help="登录轮询间隔，单位：秒")
    parser.add_argument("--timeout", type=int, help="扫码登录超时时间，单位：秒")
    _add_auth_resolution_arguments(parser)


def _add_status_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--auth",
        help="登录 Cookie，格式如 `SESSDATA=xxxxx; bili_jct=yyyyy`",
    )
    _add_auth_resolution_arguments(parser)


def _add_logout_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--auth", help=argparse.SUPPRESS)
    _add_auth_storage_arguments(parser)


def _add_auth_resolution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-x",
        "--proxy",
        help="设置代理（auto 为系统代理、no 为不使用代理、当然也可以设置代理值）",
    )
    _add_auth_storage_arguments(parser)


def _add_auth_storage_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--auth-file", type=path_from_cli, help="认证信息文件路径")
    parser.add_argument("--auth-profile", help="认证信息 profile 名称，默认 default")
    parser.add_argument("--config", help="配置文件路径")


# Compatibility entry points for tests and callers that used the old parser module.
add_login_arguments = _add_login_arguments
add_auth_status_arguments = _add_status_arguments
add_auth_logout_arguments = _add_logout_arguments
