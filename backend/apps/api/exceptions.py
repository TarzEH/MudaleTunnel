"""Translation of domain exceptions into HTTP responses.

Scope violations are the most important error this API returns, so they get a
real message rather than a generic 400 — the operator needs to see *which*
range was refused and what the engagement actually permits. That text is a
safety feature, not an internal detail.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.engagements.scope import OutOfScope, ScopeViolation, TargetSyntaxError
from apps.scans.services import PermissionDenied as ScanPermissionDenied
from apps.tunnels.pivot import PivotError
from apps.tunnels.services import PermissionDenied as TunnelPermissionDenied
from mudale_engine.specs import SpecError

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    """DRF exception handler covering the service layer's exception types."""
    if isinstance(exc, TunnelPermissionDenied | ScanPermissionDenied):
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

    if isinstance(exc, OutOfScope | TargetSyntaxError | ScopeViolation):
        # 400 rather than 403: the request is well-formed authorisation-wise,
        # but names a target this engagement does not cover.
        return Response(
            {"detail": str(exc), "code": _scope_code(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, PivotError):
        return Response(
            {"detail": str(exc), "code": "pivot_error"}, status=status.HTTP_400_BAD_REQUEST
        )

    if isinstance(exc, SpecError):
        return Response(
            {"detail": str(exc), "code": "invalid_spec"}, status=status.HTTP_400_BAD_REQUEST
        )

    return drf_exception_handler(exc, context)


def _scope_code(exc: Exception) -> str:
    if isinstance(exc, TargetSyntaxError):
        return "invalid_target"
    if isinstance(exc, OutOfScope):
        return "out_of_scope"
    return "scope_violation"
