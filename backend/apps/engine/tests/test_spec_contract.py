"""The frontend and the specs must agree on field names.

This exists because they silently did not. The New-tunnel form posted
``listen_host``/``listen_port`` while every spec expects ``local_bind``/
``local_port`` (or ``remote_bind``/``remote_port``), so creating a tunnel from
the dashboard failed validation for every kind. Nothing caught it: the backend
tests passed because they built payloads by hand, and the frontend compiled
because ``spec`` is typed as an open object.

So this test reads the actual field map out of the TSX and compares it against
the pydantic models. It is an unusual thing for a backend test to do, and it is
worth it — this is the seam where the two halves are free to drift apart
without either side noticing.

Skips itself when the frontend is not checked out, so a backend-only
environment is not blocked by it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from apps.engine.specs import SPEC_BY_KIND

FRONTEND_FORM = (
    Path(__file__).resolve().parents[4] / "frontend" / "src" / "components" / "TunnelFormModal.tsx"
)

#: Fields the form supplies outside the per-kind map, so they are expected to be
#: absent from it but present on the model.
ALWAYS_SENT = {"endpoint"}

#: Fields on the models that the form is not required to send, because the
#: schema defaults them.
OPTIONAL_ON_MODEL = {"kind"}

pytestmark = pytest.mark.skipif(
    not FRONTEND_FORM.is_file(), reason="frontend is not checked out"
)


def frontend_spec_fields() -> dict[str, list[str]]:
    """Parse SPEC_FIELDS out of TunnelFormModal.tsx."""
    source = FRONTEND_FORM.read_text()
    match = re.search(
        r"const SPEC_FIELDS: Record<TunnelKind, SpecField\[\]> = \{(.*?)\n\};",
        source,
        re.S,
    )
    assert match, "SPEC_FIELDS not found — has the form been restructured?"

    fields: dict[str, list[str]] = {}
    for kind, raw in re.findall(r"(\w+):\s*\[([^\]]*)\]", match.group(1)):
        fields[kind] = json.loads("[" + raw.replace("'", '"').rstrip(", \n") + "]")
    return fields


def test_every_tunnel_kind_is_offered_by_the_form():
    """A kind the API accepts but the form cannot build is a dead option."""
    assert set(frontend_spec_fields()) == set(SPEC_BY_KIND)


@pytest.mark.parametrize("kind", sorted(SPEC_BY_KIND))
def test_the_form_sends_exactly_the_fields_the_spec_requires(kind):
    """The regression test for listen_host/listen_port.

    ``extra="forbid"`` means a wrong name is rejected outright, and a missing
    required one is too — so any disagreement here is a 400 on every attempt to
    create that kind from the dashboard.
    """
    model_fields = set(SPEC_BY_KIND[kind].model_fields) - ALWAYS_SENT - OPTIONAL_ON_MODEL
    form_fields = set(frontend_spec_fields()[kind])

    missing = model_fields - form_fields
    unknown = form_fields - model_fields

    assert not missing, f"{kind}: the form never sends {sorted(missing)}"
    assert not unknown, f"{kind}: the form sends {sorted(unknown)}, which the spec forbids"


def test_the_form_still_sends_the_ssh_endpoint():
    """Every kind needs it, so it is built outside the per-kind map.

    Worth asserting: it was absent entirely in the version of the form that
    shipped with the wrong field names.
    """
    source = FRONTEND_FORM.read_text()
    assert "endpoint: {" in source
    for field in ("user:", "host:", "port:"):
        assert field in source, f"the endpoint block no longer sets {field}"
