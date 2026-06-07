"""ConfiDoc Backend — Audit log middleware and helpers.

Records every mutating API action and sensitive document reads to audit_logs
for RGPD traceability.
"""

from __future__ import annotations

import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger
from app.services.audit_trail_service import record_audit_event

logger = get_logger(__name__)


def _extract_user_id_from_request(request: Request) -> str | None:
    """Extrait l'user_id depuis request.state (si auth déjà résolue)
    ou depuis le JWT Authorization header (pour les routes auth comme /login).

    Retourne None si aucun utilisateur identifiable.
    """
    # Chemin rapide : auth middleware a déjà résolu l'utilisateur
    if hasattr(request.state, "user") and request.state.user:
        return str(request.state.user.id)

    # Chemin fallback : décoder le JWT nous-mêmes (best-effort, sans lever d'exception)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        from app.core.security import decode_access_token

        payload = decode_access_token(token)
        if payload and "sub" in payload:
            return str(payload["sub"])
    except Exception:
        pass
    return None


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
    (re.compile(r"/api/v1/copilot"), "copilot"),
    (re.compile(r"/api/v1/leads"), "lead"),
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

    _SENSITIVE_GET_RE = re.compile(
        r"/api/v1/documents/[0-9a-f-]{36}/"
        r"(raw|preview|export|export-pdf|export-fec|extracted-text|structured|"
        r"audit-report|audit-report-pdf|risk-score|compliance-report)"
    )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        if not request.url.path.startswith("/api/"):
            return response

        # Audit mutating methods + sensitive GET endpoints (RGPD traceability)
        should_audit = request.method in _AUDITED_METHODS
        if request.method == "GET" and self._SENSITIVE_GET_RE.search(request.url.path):
            should_audit = True

        if not should_audit:
            return response

        # Fire-and-forget: don't block the response
        try:
            await self._record_audit(request, response)
        except Exception as exc:
            logger.warning("audit_log_failed", error=str(exc))

        return response

    async def _record_audit(self, request: Request, response: Response) -> None:
        from app.core.database import async_session_factory

        user_id = _extract_user_id_from_request(request)
        org_id = None
        if hasattr(request.state, "org_id"):
            org_id = request.state.org_id

        resource_type, resource_id = _extract_resource(request.url.path)
        action = _extract_action(request.method, request.url.path)

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]
        request_id = getattr(request.state, "request_id", None)
        actor_type = "api_key" if getattr(request.state, "auth_type", "") == "api_key" else "user"

        async with async_session_factory() as session:
            from app.core.rls import set_rls_context

            await set_rls_context(session, org_id=org_id, user_id=user_id)
            await record_audit_event(
                session,
                user_id=user_id,
                org_id=org_id,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                method=request.method,
                path=str(request.url.path)[:500],
                status_code=response.status_code,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                details={
                    "query_present": bool(request.url.query),
                    "api_key_auth": actor_type == "api_key",
                },
            )
            await session.commit()
