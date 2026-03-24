"""ConfiDoc Backend — Audit log middleware and helpers.

Records every mutating API action (POST/PUT/PATCH/DELETE) to audit_logs table
for full RGPD traceability.
"""

from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)

# Only audit mutating methods on API paths
_AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Extract resource info from API paths
_RESOURCE_PATTERNS = [
    (re.compile(r"/api/v1/documents/([0-9a-f-]{36})"), "document"),
    (re.compile(r"/api/v1/uploads"), "upload"),
    (re.compile(r"/api/v1/auth"), "auth"),
    (re.compile(r"/api/v1/feedback"), "feedback"),
    (re.compile(r"/api/v1/kb"), "kb"),
    (re.compile(r"/api/v1/ai"), "ai"),
    (re.compile(r"/api/v1/users"), "user"),
]


def _extract_resource(path: str) -> tuple[str, str | None]:
    """Extract resource_type and resource_id from request path."""
    for pattern, resource_type in _RESOURCE_PATTERNS:
        m = pattern.search(path)
        if m:
            resource_id = m.group(1) if m.lastindex and m.lastindex >= 1 else None
            return resource_type, resource_id
    return "unknown", None


def _extract_action(method: str, path: str) -> str:
    """Derive a human-readable action from method + path."""
    path_lower = path.lower()

    if "restore" in path_lower:
        return "restore"
    if "anonymize" in path_lower:
        return "anonymize"
    if "validate" in path_lower:
        return "validate"
    if "export" in path_lower:
        return "export"
    if "feedback" in path_lower and method == "POST":
        return "feedback_submit"
    if "batch" in path_lower:
        return "batch_upload"
    if "/auth/token" in path_lower:
        return "login"
    if "/auth/register" in path_lower:
        return "register"

    action_map = {
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }
    return action_map.get(method, method.lower())


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Logs mutating API actions to the audit_logs table."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Only audit mutating methods on API endpoints
        if request.method not in _AUDITED_METHODS:
            return response
        if not request.url.path.startswith("/api/"):
            return response

        # Fire-and-forget: don't block the response
        try:
            await self._record_audit(request, response)
        except Exception as exc:
            logger.warning("audit_log_failed", error=str(exc))

        return response

    async def _record_audit(self, request: Request, response: Response) -> None:
        from app.core.database import async_session_factory
        from app.models.audit_log import AuditLog

        user_id = None
        org_id = None
        if hasattr(request.state, "user") and request.state.user:
            user_id = request.state.user.id
            # Try to get org_id from membership (already loaded in some paths)
            if hasattr(request.state, "org_id"):
                org_id = request.state.org_id

        resource_type, resource_id = _extract_resource(request.url.path)
        action = _extract_action(request.method, request.url.path)

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

        async with async_session_factory() as session:
            session.add(AuditLog(
                user_id=user_id,
                org_id=org_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                method=request.method,
                path=str(request.url.path)[:500],
                status_code=response.status_code,
                ip_address=ip_address,
                user_agent=user_agent,
                details=None,
            ))
            await session.commit()
