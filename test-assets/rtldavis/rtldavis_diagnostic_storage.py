"""Bounded storage retention for driver-generated diagnostic captures."""

from dataclasses import dataclass
from pathlib import Path
import re
import stat


DEFAULT_MAX_BYTES = 50 * 1024 * 1024

CAPTURE_PATTERNS = {
    "phase_c": re.compile(
        r"phase-c-\d{8}T\d{6}Z-[0-9a-f]{12,32}\.json"
    ),
    "gust": re.compile(
        r"gust-\d{8}T\d{12}Z-(?:\d{6,}|[0-9a-f]{32})\.json"
    ),
}


@dataclass(frozen=True)
class CaptureFile:
    path: Path
    kind: str
    size: int
    modified_ns: int


def list_captures(directory, kind):
    """Find regular files matching a known capture filename format."""
    pattern = CAPTURE_PATTERNS[kind]
    directory = Path(directory)

    try:
        entries = list(directory.iterdir())
    except FileNotFoundError:
        return []

    result = []

    for path in entries:
        if not pattern.fullmatch(path.name):
            continue

        try:
            info = path.lstat()
        except FileNotFoundError:
            continue

        if not stat.S_ISREG(info.st_mode):
            continue

        result.append(CaptureFile(
            path=path,
            kind=kind,
            size=info.st_size,
            modified_ns=info.st_mtime_ns,
        ))

    return sorted(
        result,
        key=lambda item: (
            item.modified_ns,
            str(item.path),
        ),
    )


def prune_captures(groups, max_bytes=DEFAULT_MAX_BYTES):
    """Apply per-group file limits and a combined byte limit.

    groups contains (directory, capture_kind, max_files) tuples.
    Only recognized capture files are eligible for deletion.

    Returns retention statistics. Filesystem errors other than
    already-removed files propagate to the caller.
    """
    max_bytes = max(0, int(max_bytes))

    remaining = {}
    removed_files = 0
    removed_bytes = 0

    def remove(item):
        nonlocal removed_files, removed_bytes

        try:
            item.path.unlink()
        except FileNotFoundError:
            return

        removed_files += 1
        removed_bytes += item.size

    for directory, kind, max_files in groups:
        limit = max(0, int(max_files))
        captures = list_captures(directory, kind)

        excess = max(0, len(captures) - limit)

        for item in captures[:excess]:
            remove(item)

        for item in captures[excess:]:
            remaining[item.path.resolve()] = item

    total = sum(item.size for item in remaining.values())

    oldest_first = sorted(
        remaining.items(),
        key=lambda pair: (
            pair[1].modified_ns,
            str(pair[1].path),
        ),
    )

    for key, item in oldest_first:
        if total <= max_bytes:
            break

        remove(item)
        total -= item.size
        del remaining[key]

    return {
        "retained_files": len(remaining),
        "retained_bytes": total,
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
    }
