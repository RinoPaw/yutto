from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any

from yutto.utils.console.logger import Logger

if TYPE_CHECKING:
    from collections.abc import Sequence


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
