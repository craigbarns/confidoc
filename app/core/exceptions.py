"""ConfiDoc Backend — Exceptions métier custom."""

from fastapi import HTTPException, status


class ConfiDocException(Exception):
    """Exception de base ConfiDoc."""

    def __init__(self, message: str = "Une erreur est survenue"):
        self.message = message
        super().__init__(self.message)


class NotFoundError(ConfiDocException):
    """Ressource introuvable."""

    pass


class PermissionDeniedError(ConfiDocException):
    """Accès refusé."""

    pass


class TenantIsolationError(ConfiDocException):
    """Violation d'isolation tenant."""

    pass


class FileValidationError(ConfiDocException):
    """Fichier uploadé invalide."""

    pass


class QuotaExceededError(ConfiDocException):
    """Quota dépassé."""

    pass


# ---------- HTTP Exceptions helpers ----------


def http_404(detail: str = "Ressource introuvable") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def http_403(detail: str = "Accès refusé") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def http_400(detail: str = "Requête invalide") -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def http_401(detail: str = "Non authentifié") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def http_409(detail: str = "Conflit") -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def http_413(detail: str = "Fichier trop volumineux") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=detail
    )
