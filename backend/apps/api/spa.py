"""Serving the built dashboard.

The SPA owns client-side routing, so any path that is not an API route, the
admin, or a static asset has to return ``index.html`` and let the router decide.
The catch-all is deliberately narrow about what it will serve — it returns one
known file and never resolves a user-supplied path against the filesystem.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.cache import never_cache

logger = logging.getLogger(__name__)

MISSING_BUILD_MESSAGE = """<!doctype html>
<title>MudaleTunnel</title>
<style>
  body { font: 15px/1.6 ui-sans-serif, system-ui, sans-serif; background:#09090b; color:#fafafa;
         display:flex; min-height:100vh; align-items:center; justify-content:center; margin:0 }
  div { max-width: 34rem; padding: 2rem }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color:#22d3ee }
  p { color:#a1a1aa }
</style>
<div>
  <h1>Dashboard not built</h1>
  <p>The API is running, but no compiled dashboard was found.</p>
  <p>Build it with <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>,
     or use the Docker image, which builds it as part of the image.</p>
  <p>The API itself is available under <code>/api/v1/</code>.</p>
</div>
"""


@never_cache
def spa(request, path: str = ""):
    """Return the SPA shell for any non-API path.

    ``path`` is captured but never used to read a file: doing so would turn
    client-side routing into an arbitrary-file-read primitive. Assets are served
    by staticfiles under ``/static/``, not from here.
    """
    index = Path(settings.FRONTEND_DIST) / "index.html"

    if not index.is_file():
        # A missing build is a deployment mistake, not a 404 — say so plainly
        # rather than letting the operator think the app is broken.
        return HttpResponse(MISSING_BUILD_MESSAGE, status=501)

    try:
        return HttpResponse(index.read_bytes(), content_type="text/html")
    except OSError:
        logger.exception("Could not read the dashboard entry point at %s", index)
        raise Http404 from None
