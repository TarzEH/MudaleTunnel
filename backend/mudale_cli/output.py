"""Terminal formatting.

Deliberately plain: aligned columns, one accent-free colour per status, and no
box-drawing. Output should stay readable when piped, redirected to a file, or
pasted into an engagement report — so colour is disabled automatically when
stdout is not a terminal, and ``--json`` prints machine-readable output instead.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

_ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}

STATUS_COLOURS = {
    "active": "green",
    "online": "green",
    "completed": "green",
    "ok": "green",
    "starting": "yellow",
    "stopping": "yellow",
    "degraded": "yellow",
    "queued": "yellow",
    "running": "yellow",
    "pending": "yellow",
    "failed": "red",
    "denied": "red",
    "error": "red",
    "timed_out": "red",
    "stopped": "grey",
    "offline": "grey",
    "retired": "grey",
    "cancelled": "grey",
}


def use_colour() -> bool:
    """Honour NO_COLOR and disable colour when piped."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("MUDALE_FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def paint(text: str, colour: str) -> str:
    if not use_colour() or colour not in _ANSI:
        return text
    return f"{_ANSI[colour]}{text}{_ANSI['reset']}"


def status_label(status: str) -> str:
    return paint(status, STATUS_COLOURS.get(status, "reset"))


def print_json(value: Any) -> None:
    json.dump(value, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def table(
    rows: list[dict], columns: list[tuple[str, str]], *, empty: str = "Nothing to show."
) -> None:
    """Print aligned columns. ``columns`` is a list of (key, header) pairs."""
    if not rows:
        print(paint(empty, "grey"))
        return

    headers = [header for _, header in columns]
    widths = [len(header) for header in headers]
    cells: list[list[str]] = []

    for row in rows:
        line = [_render(row.get(key)) for key, _ in columns]
        cells.append(line)
        for index, value in enumerate(line):
            widths[index] = max(widths[index], len(_strip_ansi(value)))

    print(paint("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip(), "dim"))
    for line in cells:
        rendered = []
        for index, value in enumerate(line):
            padding = widths[index] - len(_strip_ansi(value))
            rendered.append(value + " " * max(0, padding))
        print("  ".join(rendered).rstrip())


def detail(pairs: list[tuple[str, Any]]) -> None:
    width = max((len(label) for label, _ in pairs), default=0)
    for label, value in pairs:
        print(f"{paint(label.ljust(width), 'dim')}  {_render(value)}")


def relative_time(value: str | None) -> str:
    """Render an ISO timestamp as '3m ago'."""
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)

    seconds = (datetime.now(UTC) - moment).total_seconds()
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def error(message: str) -> None:
    print(f"{paint('error', 'red')}  {message}", file=sys.stderr)


def success(message: str) -> None:
    print(f"{paint('ok', 'green')}  {message}")


def _render(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _strip_ansi(text: str) -> str:
    """Length of the visible text, for column alignment."""
    result, index = [], 0
    while index < len(text):
        if text[index] == "\033":
            end = text.find("m", index)
            index = len(text) if end == -1 else end + 1
            continue
        result.append(text[index])
        index += 1
    return "".join(result)
