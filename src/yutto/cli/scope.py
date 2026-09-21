from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import BaseModel

    from yutto.cli.settings import YuttoConfig


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()


@dataclass(frozen=True, slots=True)
class Scope:
    """One explicit CLI/config value layer with lexical-style parent lookup."""

    values: Mapping[str, Any]
    parent: Scope | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def lookup(self, key: str) -> Any | _Missing:
        if key in self.values:
            return self.values[key]
        if self.parent is not None:
            return self.parent.lookup(key)
        return MISSING

    def flatten(self, *, stop_at: Scope | None = None) -> dict[str, Any]:
        if self is stop_at:
            return {}
        values = self.parent.flatten(stop_at=stop_at) if self.parent is not None else {}
        values.update(self.values)
        return values


_BASIC_SCOPE_NAMES = {
    "num_workers": "download_workers",
    "metadata_format_premiered": "metadata_premiered_format",
}
_BATCH_SCOPE_NAMES = {
    "batch_filter_start_time": "publication_start_time",
    "batch_filter_end_time": "publication_end_time",
}
_DANMAKU_SCOPE_NAMES = {
    "font_size": "danmaku_font_size",
    "font": "danmaku_font",
    "opacity": "danmaku_opacity",
    "display_region_ratio": "danmaku_display_region_ratio",
    "speed": "danmaku_speed",
    "block_top": "danmaku_block_top",
    "block_bottom": "danmaku_block_bottom",
    "block_scroll": "danmaku_block_scroll",
    "block_reverse": "danmaku_block_reverse",
    "block_fixed": "danmaku_block_fixed",
    "block_special": "danmaku_block_special",
    "block_colorful": "danmaku_block_colorful",
    "block_keyword_patterns": "danmaku_block_keyword_patterns",
}


def config_scope(config: YuttoConfig) -> Scope:
    """Translate explicitly configured TOML fields into the common CLI scope namespace."""

    values: dict[str, Any] = {}
    _copy_explicit(values, config.basic, _BASIC_SCOPE_NAMES)
    _copy_explicit(values, config.resource)
    _copy_explicit(values, config.danmaku, _DANMAKU_SCOPE_NAMES)
    _copy_explicit(values, config.batch, _BATCH_SCOPE_NAMES)
    _copy_explicit(values, config.auth)

    for key in ("dir", "tmp_dir", "auth_file"):
        value = values.get(key, MISSING)
        if value is not MISSING and value is not None:
            values[key] = Path(value).expanduser()

    return Scope(values)


def _copy_explicit(
    target: dict[str, Any],
    model: BaseModel,
    names: Mapping[str, str] | None = None,
) -> None:
    names = names or {}
    for field in model.model_fields_set:
        target[names.get(field, field)] = getattr(model, field)
