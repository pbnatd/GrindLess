from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .good_import import GoodInventory, import_good, load_good


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
JSON_SUFFIXES = {".json", ".good"}


class VideoInventoryExtractor(Protocol):
    """Boundary for Artiscan or a future local video-to-GOOD extractor."""

    def extract_good(self, video_path: Path) -> dict[str, object]: ...


def load_inventory_input(
    path: str | Path,
    *,
    video_extractor: VideoInventoryExtractor | None = None,
) -> GoodInventory:
    """Normalize supported user inputs into one validated GOOD inventory.

    JSON is the serialization syntax; GOOD is the schema inside that JSON.
    Video is a first-class product input but needs an explicit extractor adapter.
    The current MVP deliberately fails loud instead of pretending to parse video.
    """

    source_path = Path(path)
    suffix = source_path.suffix.lower()
    if suffix in JSON_SUFFIXES:
        return load_good(source_path)
    if suffix in VIDEO_SUFFIXES:
        if video_extractor is None:
            raise ValueError(
                "video inventory input requires a configured Artiscan-compatible "
                "extractor; process the video in Artiscan and provide its JSON export"
            )
        return import_good(video_extractor.extract_good(source_path))
    raise ValueError(
        f"unsupported inventory input {suffix or '<no extension>'!r}; "
        "expected GOOD-compatible .json/.good or .mp4/.mov/.mkv/.webm video"
    )
