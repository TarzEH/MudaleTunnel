"""HTTP client for the MudaleTunnel API.

The CLI deliberately talks to the same REST API as the dashboard rather than
importing Django and touching the ORM. Two reasons:

* Anything done in the terminal appears in the browser immediately, because both
  are the same writes going through the same service layer and the same audit
  trail — there is no "CLI mode" with different rules.
* The CLI runs anywhere, including a laptop that is not the engine host.

Uses only the standard library so the CLI has no dependencies of its own.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://127.0.0.1:8000"
#: Only real network schemes. Without this check a MUDALE_URL of "file:///etc/"
#: would make urllib read local files and hand them back as an API response.
ALLOWED_SCHEMES = frozenset({"http", "https"})
CONFIG_PATH = Path(os.environ.get("MUDALE_CONFIG", "~/.config/mudale/config.json")).expanduser()
TIMEOUT_SECONDS = 30


class ApiError(Exception):
    """A non-2xx response. ``detail`` carries the server's explanation."""

    def __init__(self, status: int, detail: str, code: str = "", payload: Any = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code
        self.payload = payload


class Config:
    """CLI configuration: where the server is and which key to use."""

    def __init__(self, url: str, token: str = ""):
        self.url = _validate_url(url)
        self.token = token

    @classmethod
    def load(cls) -> Config:
        """Environment wins over the config file, so CI can override cleanly."""
        url = os.environ.get("MUDALE_URL", "")
        token = os.environ.get("MUDALE_TOKEN", "")

        if (not url or not token) and CONFIG_PATH.is_file():
            try:
                stored = json.loads(CONFIG_PATH.read_text())
            except (OSError, json.JSONDecodeError):
                stored = {}
            url = url or stored.get("url", "")
            token = token or stored.get("token", "")

        return cls(url or DEFAULT_URL, token)

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({"url": self.url, "token": self.token}, indent=2))
        # The file holds an API key, so it must not be world-readable.
        CONFIG_PATH.chmod(0o600)
        CONFIG_PATH.parent.chmod(0o700)


def _validate_url(url: str) -> str:
    """Reject anything that is not an http(s) endpoint."""
    cleaned = (url or "").rstrip("/")
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        raise ValueError(f"Server URL must be http:// or https:// — got {url!r}")
    return cleaned


class Client:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()

    # ── Verbs ───────────────────────────────────────────────────────────

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict | None = None) -> Any:
        return self._request("POST", path, body=body)

    def patch(self, path: str, body: dict | None = None) -> Any:
        return self._request("PATCH", path, body=body)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def paged(self, path: str, params: dict | None = None) -> list[dict]:
        """Follow pagination and return every result."""
        results: list[dict] = []
        payload = self.get(path, params)
        while True:
            if isinstance(payload, list):
                return payload
            results.extend(payload.get("results", []))
            next_url = payload.get("next")
            if not next_url:
                return results
            payload = self._request("GET", next_url, absolute=True)

    # ── Transport ───────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        absolute: bool = False,
    ) -> Any:
        url = path if absolute else f"{self.config.url}/api/v1{path}"
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url = f"{url}?{urllib.parse.urlencode(filtered)}"

        # Re-check after any redirect-provided or paginated absolute URL: the
        # server controls `next`, so it must not be able to redirect us to file:.
        _validate_url(url)

        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if self.config.token:
            request.add_header("Authorization", f"Bearer {self.config.token}")

        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise self._to_api_error(exc) from None
        except urllib.error.URLError as exc:
            raise ApiError(
                0,
                f"Could not reach {self.config.url}: {exc.reason}. "
                f"Is the server running, and is MUDALE_URL correct?",
            ) from None

    @staticmethod
    def _to_api_error(exc: urllib.error.HTTPError) -> ApiError:
        try:
            payload = json.loads(exc.read())
        except (ValueError, OSError):
            payload = {}

        if isinstance(payload, dict):
            detail = payload.get("detail")
            if not detail:
                # DRF field errors: surface them rather than a bare status code.
                parts = [
                    f"{field}: {'; '.join(map(str, msgs)) if isinstance(msgs, list) else msgs}"
                    for field, msgs in payload.items()
                ]
                detail = " | ".join(parts) if parts else exc.reason
            return ApiError(exc.code, str(detail), payload.get("code", ""), payload)

        return ApiError(exc.code, str(payload) or exc.reason)
