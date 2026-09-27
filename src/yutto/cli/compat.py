from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from yutto.utils.console.logger import Logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any


SUBCOMMANDS = ("download", "auth", "serve")
LEGACY_AUTH_SUBCOMMANDS = ("login",)


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """Rewrite legacy CLI invocations into the current command grammar."""
    normalized = list(argv)
    if not normalized:
        return ["download"]

    command_index = 0
    while command_index < len(normalized):
        token = normalized[command_index]
        if token == "--config":
            if command_index + 1 >= len(normalized):
                return normalized
            command_index += 2
            continue
        if token.startswith("--config="):
            command_index += 1
            continue
        break

    if command_index >= len(normalized):
        return normalized

    command = normalized[command_index]
    if command in {"-v", "--version"}:
        return normalized
    if command in LEGACY_AUTH_SUBCOMMANDS:
        return [*normalized[:command_index], "auth", *normalized[command_index:]]
    if command not in SUBCOMMANDS:
        return [*normalized[:command_index], "download", *normalized[command_index:]]
    return normalized


class DeprecatedExtraEpisodesAction(argparse.Action):
    def __init__(self, option_strings: Sequence[str], dest: str, **kwargs: Any):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        Logger.deprecated_warning(f"参数 {option_string} 已弃用，推荐改用 --with-extra-episodes")
        setattr(namespace, self.dest, True)
