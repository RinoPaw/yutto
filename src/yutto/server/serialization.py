from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, TypeAlias, TypeVar

from yutto.core.result import DownloadResult, ItemResult, ResolveFailure, ResolveResult
from yutto.media import (
    BangumiEpisode,
    BangumiSeason,
    CheeseEpisode,
    CheeseSeason,
    Media,
    UgcAllFavourites,
    UgcCollection,
    UgcFav,
    UgcPage,
    UgcSeries,
    UgcSpace,
    UgcVideo,
    UgcWatchLater,
)
from yutto.scope import Scope
from yutto.types import BilibiliId
from yutto.utils.metadata import ItemMetaData

if TYPE_CHECKING:
    from yutto.runtime import EventReplay, TaskEvent, TaskSnapshot

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
PayloadT = TypeVar("PayloadT")
ResultT = TypeVar("ResultT")

_CREDENTIAL_FIELDS = frozenset(
    {
        "api_key",
        "auth",
        "authorization",
        "bili_jct",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "password",
        "secret",
        "sessdata",
        "token",
    }
)

# The RPC payload is an explicit projection of Scope. Adding an internal Scope
# field therefore cannot silently extend the public wire schema.
_SCOPE_WIRE_FIELDS = (
    "source.value",
    "selection.expression",
    "selection.with_extra_episodes",
    "selection.skip_preview",
    "selection.published_since",
    "selection.published_before",
    "runtime.jobs",
    "runtime.ffmpeg_path",
    "runtime.preview_formats",
    "runtime.no_color",
    "runtime.no_progress",
    "runtime.debug",
    "auth.profile",
    "auth.login_strict",
    "auth.vip_strict",
    "auth.mode",
    "auth.poll_interval",
    "auth.timeout",
    "resource.video",
    "resource.audio",
    "resource.danmaku",
    "resource.subtitle",
    "resource.metadata",
    "resource.cover",
    "resource.chapter_info",
    "resource.save_cover",
    "resource.ai_translation_language",
    "stream.video_quality",
    "stream.audio_quality",
    "stream.video_codec",
    "stream.audio_codec",
    "stream.video_codec_priority",
    "output.format",
    "output.audio_only_format",
    "output.directory",
    "output.temporary_directory",
    "output.overwrite",
    "output.subpath_template",
    "output.metadata_premiered_format",
    "network.proxy",
    "network.fetch_workers",
    "network.download_workers",
    "network.block_size",
    "network.download_interval",
    "network.banned_mirrors_pattern",
    "danmaku.format",
    "danmaku.font_size",
    "danmaku.font",
    "danmaku.opacity",
    "danmaku.display_region_ratio",
    "danmaku.speed",
    "danmaku.block_top",
    "danmaku.block_bottom",
    "danmaku.block_scroll",
    "danmaku.block_reverse",
    "danmaku.block_fixed",
    "danmaku.block_special",
    "danmaku.block_colorful",
    "danmaku.block_keyword_patterns",
)


def snapshot_to_json(snapshot: TaskSnapshot[PayloadT, ResultT]) -> dict[str, object]:
    """Project one task snapshot onto the stable RPC schema."""
    result = snapshot_summary_to_json(snapshot)
    if snapshot.error is not None:
        error: dict[str, JsonValue] = {
            "code": snapshot.error.code,
            "type": snapshot.error.type,
            "message": snapshot.error.message,
        }
        if snapshot.error.truncated:
            error["truncated"] = True
        result["error"] = error
    result["payload"] = _snapshot_payload_to_json(snapshot.payload)
    result["result"] = _snapshot_result_to_json(snapshot.result)
    return result


def snapshot_summary_to_json(snapshot: TaskSnapshot[PayloadT, ResultT]) -> dict[str, object]:
    error: dict[str, JsonValue] | None = None
    if snapshot.error is not None:
        error = {"code": snapshot.error.code, "type": snapshot.error.type}
        if snapshot.error.truncated:
            error["truncated"] = True
    return {
        "task_id": snapshot.task_id,
        "state": snapshot.state.value,
        "error": error,
        "created_at": snapshot.created_at.isoformat(),
        "started_at": snapshot.started_at.isoformat() if snapshot.started_at is not None else None,
        "finished_at": snapshot.finished_at.isoformat() if snapshot.finished_at is not None else None,
        "last_event_seq": snapshot.last_event_seq,
    }


def event_to_json(event: TaskEvent) -> dict[str, object]:
    """Serialize the already-explicit runtime event payload."""
    return {
        "task_id": event.task_id,
        "seq": event.seq,
        "kind": event.kind,
        "state": event.state.value,
        "created_at": event.created_at.isoformat(),
        "data": _wire_value(event.data),
    }


def replay_to_json(replay: EventReplay) -> dict[str, object]:
    return {
        "task_id": replay.task_id,
        "after_seq": replay.after_seq,
        "events": [event_to_json(event) for event in replay.events],
        "truncated": replay.truncated,
    }


def _snapshot_payload_to_json(payload: object) -> JsonValue:
    if isinstance(payload, Scope):
        return _scope_to_json(payload)
    raise TypeError(f"unsupported RPC task payload: {type(payload).__name__}")


def _snapshot_result_to_json(result: object) -> JsonValue:
    if result is None:
        return None
    if isinstance(result, DownloadResult):
        return _download_result_to_json(result)
    if isinstance(result, ResolveResult):
        return _resolve_result_to_json(result)
    raise TypeError(f"unsupported RPC task result: {type(result).__name__}")


def _scope_to_json(scope: Scope) -> dict[str, JsonValue]:
    flattened = scope.flatten()
    result: dict[str, JsonValue] = {}
    for path in _SCOPE_WIRE_FIELDS:
        if path not in flattened:
            continue
        section, field = path.split(".", 1)
        value = flattened[path]
        section_value = result.setdefault(section, {})
        assert isinstance(section_value, dict)
        if path == "network.proxy" and isinstance(value, str):
            section_value[field] = _sanitize_proxy(value)
        else:
            section_value[field] = _wire_value(value)
    return result


def _download_result_to_json(result: DownloadResult) -> dict[str, JsonValue]:
    return {"items": [_item_result_to_json(item) for item in result.items]}


def _item_result_to_json(item: ItemResult) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {
        "planned_path": _path_to_json(item.planned_path),
        "state": item.state.value,
        "output_path": _path_to_json(item.output_path),
        "skip_reason": item.skip_reason.value if item.skip_reason is not None else None,
        "artifacts": [
            {
                "kind": artifact.kind.value,
                "path": artifact.path.as_posix(),
            }
            for artifact in item.artifacts
        ],
    }
    if item.failure is not None:
        result["failure"] = {
            "type": item.failure.type,
            "message": item.failure.message,
            "code": _wire_value(item.failure.code),
        }
    return result


def _resolve_result_to_json(result: ResolveResult) -> dict[str, JsonValue]:
    return {
        "items": [_media_to_json(item) for item in result.items],
        "failures": [_resolve_failure_to_json(failure) for failure in result.failures],
    }


def _resolve_failure_to_json(failure: ResolveFailure) -> dict[str, JsonValue]:
    return {
        "path": [
            {"index": step.index, "source": step.source}
            for step in failure.path
        ],
        "type": failure.type,
        "message": failure.message,
        "code": _wire_value(failure.code),
    }


def _media_to_json(media: Media) -> dict[str, JsonValue]:
    base: dict[str, JsonValue] = {
        "type": type(media).__name__,
        "metadata": _metadata_to_json(media.metadata),
    }

    if isinstance(media, BangumiEpisode):
        base.update(
            {
                "index": media.index,
                "episode_id": str(media.episode_id),
                "aid": str(media.aid),
                "cid": str(media.cid),
                "is_preview": media.is_preview,
            }
        )
    elif isinstance(media, BangumiSeason):
        base.update(
            {
                "season_id": str(media.season_id),
                "items": [_media_to_json(item) for item in media.items],
            }
        )
    elif isinstance(media, CheeseEpisode):
        base.update(
            {
                "index": media.index,
                "episode_id": str(media.episode_id),
                "aid": str(media.aid),
                "cid": str(media.cid),
            }
        )
    elif isinstance(media, CheeseSeason):
        base.update(
            {
                "season_id": str(media.season_id),
                "items": [_media_to_json(item) for item in media.items],
            }
        )
    elif isinstance(media, UgcPage):
        base.update(
            {
                "index": media.index,
                "aid": str(media.aid),
                "cid": str(media.cid),
            }
        )
    elif isinstance(media, UgcVideo):
        base.update(
            {
                "aid": str(media.aid),
                "page_count": media.page_count,
                "items": [_media_to_json(item) for item in media.items],
            }
        )
    elif isinstance(media, UgcCollection):
        base.update(
            {
                "collection_id": str(media.collection_id),
                "items": [_media_to_json(item) for item in media.items],
            }
        )
    elif isinstance(media, UgcSeries):
        base.update(
            {
                "series_id": str(media.series_id),
                "items": [_media_to_json(item) for item in media.items],
            }
        )
    elif isinstance(media, UgcFav):
        base.update(
            {
                "fid": str(media.fid),
                "items": [_media_to_json(item) for item in media.items],
            }
        )
    elif isinstance(media, UgcAllFavourites):
        base.update(
            {
                "mid": str(media.mid),
                "items": [_media_to_json(item) for item in media.items],
            }
        )
    elif isinstance(media, UgcWatchLater):
        base["items"] = [_media_to_json(item) for item in media.items]
    elif isinstance(media, UgcSpace):
        base.update(
            {
                "mid": str(media.mid),
                "items": [_media_to_json(item) for item in media.items],
            }
        )
    else:
        raise TypeError(f"unsupported RPC media type: {type(media).__name__}")

    return base


def _metadata_to_json(metadata: ItemMetaData) -> dict[str, JsonValue]:
    return {
        "title": metadata.title,
        "plot": metadata.plot,
        "published_at": metadata.published_at,
        "duration": metadata.duration,
        "mid": str(metadata.mid) if metadata.mid is not None else None,
        "owner": metadata.owner,
        "thumb": metadata.thumb,
        "show_title": metadata.show_title,
        "genre": list(metadata.genre),
        "tag": list(metadata.tag),
        "actors": [
            {
                "name": actor["name"],
                "role": actor["role"],
                "thumb": actor["thumb"],
                "profile": actor["profile"],
                "order": actor["order"],
            }
            for actor in metadata.actors
        ],
        "added_at": metadata.added_at,
        "source": metadata.source,
        "original_filename": metadata.original_filename,
        "website": metadata.website,
        "chapter_info_data": [
            {
                "start": chapter["start"],
                "end": chapter["end"],
                "content": chapter["content"],
            }
            for chapter in metadata.chapter_info_data
        ],
    }


def _wire_value(value: object) -> JsonValue:
    if isinstance(value, Enum):
        return _wire_value(value.value)
    if isinstance(value, BilibiliId):
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            json_key = str(key)
            if _is_credential_field(json_key):
                continue
            if json_key.casefold() == "proxy" and isinstance(item, str):
                result[json_key] = _sanitize_proxy(item)
            else:
                result[json_key] = _wire_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_wire_value(item) for item in value]
    raise TypeError(f"value of type {type(value).__name__} is not part of the RPC wire schema")


def _path_to_json(path: Path | None) -> str | None:
    return path.as_posix() if path is not None else None


def _is_credential_field(field: str) -> bool:
    normalized = field.casefold().replace("-", "_")
    return normalized in _CREDENTIAL_FIELDS or normalized.endswith(
        ("_api_key", "_cookie", "_credential", "_password", "_secret", "_token")
    )


def _sanitize_proxy(proxy: str) -> str:
    scheme_separator = proxy.find("://")
    if scheme_separator < 0:
        return proxy

    authority_start = scheme_separator + 3
    authority_end = len(proxy)
    for separator in "/?#":
        if (index := proxy.find(separator, authority_start)) >= 0:
            authority_end = min(authority_end, index)
    credential_separator = proxy.rfind("@", authority_start, authority_end)
    if credential_separator < 0:
        return proxy
    return f"{proxy[: scheme_separator + 3]}{proxy[credential_separator + 1 :]}"
