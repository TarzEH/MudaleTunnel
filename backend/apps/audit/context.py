"""Ambient request context for audit writes.

Recording an audit event needs the actor, the request id and the source IP.
Threading those through every call site would mean touching every function
signature down to the engine adapters, so they live in context variables that
the middleware populates and :func:`apps.audit.services.record` reads.

Context variables (not thread locals) so the values follow ``await`` boundaries
correctly under ASGI.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

SYSTEM_ACTOR_LABEL = "system"


@dataclass(frozen=True)
class AuditContext:
    actor: Any | None = None
    actor_label: str = SYSTEM_ACTOR_LABEL
    request_id: str = ""
    source_ip: str | None = None
    #: The in-flight request, when there is one.
    #:
    #: Held so the actor can be resolved *at write time* rather than when the
    #: context is created. Middleware runs before authentication, so
    #: ``request.user`` is not known yet when the context is installed — without
    #: this, every API- and CLI-driven action would be attributed to "system"
    #: and the audit trail could not say who did anything.
    request: Any | None = None

    def resolved_actor(self) -> tuple[Any | None, str]:
        """The actor and its label, resolving from the request if needed."""
        if self.actor is not None:
            return self.actor, self.actor_label

        user = getattr(self.request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user, str(user)

        return None, self.actor_label or SYSTEM_ACTOR_LABEL


#: Default is None rather than an AuditContext instance: a ContextVar default is
#: shared by every context that never sets one, so it must not be a value anyone
#: could mutate. :func:`get_context` substitutes a fresh system context instead.
_current: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)


def get_context() -> AuditContext:
    return _current.get() or AuditContext()


def set_context(context: AuditContext):
    return _current.set(context)


def reset_context(token) -> None:
    _current.reset(token)


@contextlib.contextmanager
def using(context: AuditContext):
    """Temporarily install an audit context (used by the engine daemon)."""
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)
