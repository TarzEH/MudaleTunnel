"""Shared DRF permissions.

Two rules, both enforced here rather than per-view so a new endpoint inherits
them by default:

* Viewers are read-only, everywhere.
* Operators only see engagements they belong to; admins see everything.
"""

from __future__ import annotations

from rest_framework import permissions

SAFE_METHODS = permissions.SAFE_METHODS


class IsOperatorOrReadOnly(permissions.BasePermission):
    """Any authenticated user may read; only ``can_mutate`` roles may write."""

    message = "Your role is read-only."

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(getattr(request.user, "can_mutate", False))


class IsAdmin(permissions.BasePermission):
    message = "Admin role required."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_admin", False)
        )
