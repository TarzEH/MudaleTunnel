"""Typed environment-variable readers.

Settings modules use these instead of bare ``os.environ`` so that a missing or
malformed value fails loudly at import time rather than silently defaulting to
something insecure.
"""

import os

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class ImproperlyConfigured(Exception):
    """Raised when a required environment variable is missing or unparseable."""


def env_str(name: str, *, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        if required:
            raise ImproperlyConfigured(f"Environment variable {name} is required but not set")
        if default is None:
            raise ImproperlyConfigured(f"Environment variable {name} has no value and no default")
        return default
    return value


def env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    lowered = raw.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ImproperlyConfigured(f"Environment variable {name}={raw!r} is not a valid boolean")


def env_int(name: str, *, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"Environment variable {name}={raw!r} is not a valid integer"
        ) from exc


def env_list(name: str, *, default: list[str] | None = None) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]
