"""ConfiDoc Backend — Upload Endpoints (v2) with Streaming."""

import contextlib
import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.exceptions import http_400, http_413
from app.core.logging import get_logger
from app.core.sandbox import SandboxError, scan_file_for_malware
from app.models.client import Client
from app.models.dossier import Dossier
from app.models.document import Document, DocumentStatus
from app.models.membership import Membership
from app.rate_limit import limiter
from app.services.anonymization_service import HAS_OCR
from app.services.doc_metadata_service import build_metadata_suggestions
from app.services.integration_service import (
    build_request_hash,
    get_idempotency_replay,
    store_idempotency_response,
)
from app.services.storage_service import store_file
from app.workers.tasks import (
    anonymize_document_task,
    run_anonymize_document_inline,
    should_dispatch_document_task_to_celery,
)

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)

# Maximum number of files in a single batch upload
MAX_BATCH_SIZE = 20
CHUNK_SIZE = 8192  # 8KB
AnonymizationProfile = Literal[
    "moderate",
    "strict",
    "dataset_strict",
    "dataset_accounting",
    "dataset_accounting_pseudo",
]


def _normalize_client_name(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return re.sub(r"\s+", " ", raw)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Uploader un document (Streaming)",
)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_document(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),  # noqa: B008
    auto_anonymize: bool = Query(default=True),
    profile: str = Query(default="moderate", description="moderate|strict|internal_review|external_sharing"),  # noqa: B008
    document_type: str = Query(default="auto"),
    client_name: str = Query(default=""),
    client_id: uuid.UUID | None = Query(default=None),
    dossier_id: uuid.UUID | None = Query(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    exercice: str = Query(default=""),
    doc_category: str = Query(default=""),
) -> dict:
    """Upload un document via streaming vers un fichier temporaire pour éviter l'OOM."""
    # Map intuitive modes
    if profile == "internal_review":
        profile = "moderate"
    elif profile == "external_sharing":
        profile = "strict"

    filename = file.filename or ""
    if "." not in filename:
        raise http_400("Nom de fichier invalide")

    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise http_400(
            f"Extension non autorisée. Autorisées: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    # SEC-014 Sandbox/Antivirus could be triggered here

    # Streaming save to temp file
    temp_fd, temp_path = tempfile.mkstemp(suffix=f".{extension}")
    sha256_hash = hashlib.sha256()
    size = 0

    try:
        with os.fdopen(temp_fd, "wb") as tmp:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.max_upload_size_bytes:
                    raise http_413(
                        f"Fichier trop volumineux. Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB"
                    )
                tmp.write(chunk)
                sha256_hash.update(chunk)

        if size == 0:
            raise http_400("Fichier vide")

        # SEC-014: Sandbox antivirus / MIME verification
        try:
            scan_file_for_malware(temp_path, extension)
        except SandboxError as scan_err:
            raise http_400(f"Fichier rejeté : {str(scan_err)}") from scan_err

        org_id = getattr(request.state, "org_id", None)
        request_hash = build_request_hash({
            "route": "POST /api/v1/uploads",
            "filename": filename,
            "extension": extension,
            "size": size,
            "sha256": sha256_hash.hexdigest(),
            "auto_anonymize": auto_anonymize,
            "profile": profile,
            "document_type": document_type,
            "client_name": _normalize_client_name(client_name),
        })
        replay = await get_idempotency_replay(
            db,
            user_id=current_user.id,
            route="POST /api/v1/uploads",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if replay:
            response.status_code = replay.status_code
            response.headers["X-ConfiDoc-Idempotent-Replay"] = "true"
            return replay.response_body

        return await _upload_document_body(
            db=db,
            current_user=current_user,
            file=file,
            file_path=Path(temp_path),
            filename=filename,
            extension=extension,
            size=size,
            sha256=sha256_hash.hexdigest(),
            auto_anonymize=auto_anonymize,
            profile=profile,
            document_type=document_type,
            client_name=client_name,
            client_id=client_id,
            dossier_id=dossier_id,
            exercice=exercice,
            doc_category=doc_category,
            background_tasks=background_tasks,
            org_id_override=org_id,
            idempotency_key=idempotency_key,
            idempotency_route="POST /api/v1/uploads",
            idempotency_request_hash=request_hash,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("upload_document_failed", filename=filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du traitement du document. Veuillez réessayer.",
        ) from exc
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


async def _upload_document_body(
    *,
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile,
    file_path: Path,
    filename: str,
    extension: str,
    size: int,
    sha256: str,
    auto_anonymize: bool,
    profile: str,
    document_type: str,
    client_name: str = "",
    client_id: uuid.UUID | None = None,
    dossier_id: uuid.UUID | None = None,
    exercice: str = "",
    doc_category: str = "",
    background_tasks: BackgroundTasks | None = None,
    org_id_override: object | None = None,
    idempotency_key: str | None = None,
    idempotency_route: str | None = None,
    idempotency_request_hash: str | None = None,
) -> dict:
    """Corps métier upload (utilisant le fichier temporaire)."""
    org_id = org_id_override
    if org_id is None:
        membership_res = await db.execute(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.is_active.is_(True),
            )
        )
        membership = membership_res.scalar_one_or_none()
        org_id = membership.org_id if membership else None

    # Resolve Client
    resolved_client_id = client_id
    resolved_client_name = _normalize_client_name(client_name)

    if resolved_client_id:
        client_res = await db.execute(
            select(Client).where(Client.id == resolved_client_id, Client.org_id == org_id)
        )
        client = client_res.scalar_one_or_none()
        if not client:
            raise http_404("Client spécifié non trouvé")
        resolved_client_name = client.name
    elif resolved_client_name:
        # Try to find existing client by name in this org (case-insensitive)
        client_res = await db.execute(
            select(Client).where(
                Client.name.ilike(resolved_client_name),
                Client.org_id == org_id,
                Client.is_deleted.is_(False)
            )
        )
        client = client_res.scalar_one_or_none()
        if client:
            resolved_client_id = client.id
            resolved_client_name = client.name
        else:
            # Auto-create client
            client = Client(name=resolved_client_name, org_id=org_id)
            db.add(client)
            await db.flush()
            resolved_client_id = client.id

    if not resolved_client_name:
        raise http_400("Le nom du client ou client_id est obligatoire")

    # Resolve Dossier (Exercice)
    resolved_dossier_id = dossier_id
    # Best-effort text extraction for suggestions
    raw_text = ""
    try:
        from app.services.anonymization_service import extract_text_from_file
        raw_text = await extract_text_from_file(file_path.read_bytes(), extension) or ""
    except Exception:
        pass

    # Load known clients for smarter suggestion
    known_clients_res = await db.execute(
        select(Client.name).where(Client.org_id == org_id, Client.is_deleted.is_(False))
    )
    known_clients = [str(r) for r in known_clients_res.scalars().all()]

    suggestions = build_metadata_suggestions(raw_text, filename, [], known_clients=known_clients)
    resolved_exercice = exercice.strip() or suggestions["exercice"] or None
    resolved_doc_category = doc_category.strip() or suggestions["doc_category"] or None

    if resolved_dossier_id:
        dossier_res = await db.execute(
            select(Dossier).where(Dossier.id == resolved_dossier_id, Dossier.org_id == org_id)
        )
        dossier = dossier_res.scalar_one_or_none()
        if not dossier:
            raise http_404("Dossier spécifié non trouvé")
        resolved_exercice = dossier.exercice
        resolved_client_id = dossier.client_id
    elif resolved_client_id and resolved_exercice:
        # Try to find or create dossier
        dossier_res = await db.execute(
            select(Dossier).where(
                Dossier.client_id == resolved_client_id,
                Dossier.exercice == resolved_exercice,
                Dossier.is_deleted.is_(False)
            )
        )
        dossier = dossier_res.scalar_one_or_none()
        if not dossier:
            dossier = Dossier(client_id=resolved_client_id, exercice=resolved_exercice, org_id=org_id)
            db.add(dossier)
            await db.flush()
        resolved_dossier_id = dossier.id

    # Store to external storage
    try:
        storage_backend, storage_key = store_file(file_path=file_path, extension=extension)
    except Exception as exc:
        logger.warning("external_storage_failed", error=str(exc))
        storage_backend = "database"
        from uuid import uuid4
        storage_key = f"db://{sha256}.{uuid4().hex}.{extension}"

    uploaded_by_snapshot = str(current_user.id)

    document = Document(
        org_id=org_id,
        uploaded_by_user_id=current_user.id,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
        extension=extension,
        size_bytes=size,
        sha256=sha256,
        storage_backend=storage_backend,
        storage_key=storage_key,
        status=DocumentStatus.UPLOADED,
        raw_content=file_path.read_bytes() if storage_backend == "database" else None,
        tags=[resolved_client_name],
        client_name=resolved_client_name,
        client_id=resolved_client_id,
        dossier_id=resolved_dossier_id,
        exercice=resolved_exercice,
        doc_category=resolved_doc_category,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    logger.info(
        "document_uploaded",
        doc_id=str(document.id),
        filename=filename,
        size=size,
        backend=storage_backend,
        client_name=normalized_client_name,
        exercice=resolved_exercice,
        doc_category=resolved_doc_category,
    )

    processing: dict = {
        "auto_anonymize": auto_anonymize,
        "profile": profile,
        "document_type": document_type,
        "ocr_available": HAS_OCR,
    }

    if auto_anonymize:
        doc_id = str(document.id)
        if should_dispatch_document_task_to_celery(queue="nlp"):
            try:
                anonymize_document_task.delay(
                    doc_id=doc_id,
                    profile=profile,
                    document_type=document_type,
                )
                processing.update({"status": "processing", "background_processing": "celery"})
            except Exception as exc:
                logger.warning(
                    "celery_enqueue_failed_using_inline_background",
                    doc_id=doc_id,
                    error=str(exc),
                )
                if background_tasks is not None:
                    background_tasks.add_task(
                        run_anonymize_document_inline,
                        doc_id=doc_id,
                        profile=profile,
                        document_type=document_type,
                    )
                    processing.update({"status": "processing", "background_processing": "api"})
                else:
                    processing.update({"status": "uploaded", "background_processing": False})
        elif background_tasks is not None:
            logger.warning("celery_workers_unavailable_using_inline_background", doc_id=doc_id)
            background_tasks.add_task(
                run_anonymize_document_inline,
                doc_id=doc_id,
                profile=profile,
                document_type=document_type,
            )
            processing.update({"status": "processing", "background_processing": "api"})
        else:
            processing.update({"status": "uploaded", "background_processing": False})

    result = {
        "status": document.status.value,
        "document_id": str(document.id),
        "storage_backend": document.storage_backend,
        "sha256": document.sha256,
        "original_filename": filename,
        "content_type": file.content_type,
        "size_bytes": size,
        "uploaded_by": uploaded_by_snapshot,
        "client_name": normalized_client_name,
        "exercice": resolved_exercice,
        "doc_category": resolved_doc_category,
        "processing": processing,
        "suggestions": {
            "client_suggestion": suggestions["client_suggestion"],
            "exercice_detected": suggestions["exercice"],
            "doc_category_detected": suggestions["doc_category"],
            "auto_filled": [
                k for k, v in [
                    ("exercice", not exercice.strip() and suggestions["exercice"]),
                    ("doc_category", not doc_category.strip() and suggestions["doc_category"]),
                ]
                if v
            ],
        },
    }
    await store_idempotency_response(
        db,
        user_id=current_user.id,
        org_id=org_id,
        route=idempotency_route or "",
        idempotency_key=idempotency_key,
        request_hash=idempotency_request_hash or "",
        response_body=result,
        status_code=status.HTTP_201_CREATED,
        document_id=document.id,
    )
    return result


@router.post(
    "/batch",
    status_code=status.HTTP_200_OK,
    summary="Upload et traiter plusieurs documents en batch (Streaming)",
)
@limiter.limit("10/minute")
async def upload_batch(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),  # noqa: B008
    auto_anonymize: bool = Query(default=True),
    profile: AnonymizationProfile = Query(default="moderate"),  # noqa: B008
    document_type: str = Query(default="auto"),
    client_name: str = Query(default=""),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    exercice: str = Query(default=""),
    doc_category: str = Query(default=""),
) -> dict:
    """Upload multiple documents at once via streaming."""
    if len(files) > MAX_BATCH_SIZE:
        raise http_400(f"Maximum {MAX_BATCH_SIZE} fichiers par batch. Reçu: {len(files)}.")
    if not files:
        raise http_400("Aucun fichier fourni.")

    org_id = getattr(request.state, "org_id", None)
    if idempotency_key:
        temp_uploads: list[dict] = []
        try:
            for file in files:
                filename = file.filename or ""
                if "." not in filename:
                    raise http_400("Nom de fichier invalide (pas d'extension)")

                extension = filename.rsplit(".", 1)[1].lower()
                if extension not in settings.ALLOWED_EXTENSIONS:
                    raise http_400(f"Extension .{extension} non autorisée")

                temp_fd, temp_path = tempfile.mkstemp(suffix=f".{extension}")
                sha256_hash = hashlib.sha256()
                size = 0
                with os.fdopen(temp_fd, "wb") as tmp:
                    while chunk := await file.read(CHUNK_SIZE):
                        size += len(chunk)
                        if size > settings.max_upload_size_bytes:
                            raise http_413(
                                "Fichier trop volumineux. "
                                f"Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB"
                            )
                        tmp.write(chunk)
                        sha256_hash.update(chunk)

                if size == 0:
                    raise http_400("Fichier vide")

                try:
                    scan_file_for_malware(temp_path, extension)
                except SandboxError as scan_err:
                    raise http_400(f"Fichier rejeté : {str(scan_err)}") from scan_err

                temp_uploads.append({
                    "file": file,
                    "temp_path": temp_path,
                    "filename": filename,
                    "extension": extension,
                    "size": size,
                    "sha256": sha256_hash.hexdigest(),
                })

            request_hash = build_request_hash({
                "route": "POST /api/v1/uploads/batch",
                "files": [
                    {
                        "filename": item["filename"],
                        "extension": item["extension"],
                        "size": item["size"],
                        "sha256": item["sha256"],
                    }
                    for item in temp_uploads
                ],
                "auto_anonymize": auto_anonymize,
                "profile": profile,
                "document_type": document_type,
                "client_name": _normalize_client_name(client_name),
            })
            replay = await get_idempotency_replay(
                db,
                user_id=current_user.id,
                route="POST /api/v1/uploads/batch",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            if replay:
                response.status_code = replay.status_code
                response.headers["X-ConfiDoc-Idempotent-Replay"] = "true"
                return replay.response_body

            batch_results: list[dict] = []
            succeeded = 0
            failed = 0
            for item in temp_uploads:
                try:
                    result = await _upload_document_body(
                        db=db,
                        current_user=current_user,
                        file=item["file"],
                        file_path=Path(item["temp_path"]),
                        filename=item["filename"],
                        extension=item["extension"],
                        size=item["size"],
                        sha256=item["sha256"],
                        auto_anonymize=auto_anonymize,
                        profile=profile,
                        document_type=document_type,
                        client_name=client_name,
                        background_tasks=background_tasks,
                        org_id_override=org_id,
                    )
                    batch_results.append(result)
                    succeeded += 1
                except Exception as exc:
                    await db.rollback()
                    failed += 1
                    batch_results.append({
                        "status": "error",
                        "original_filename": item["filename"],
                        "error": str(exc)[:500],
                    })

            final_result = {
                "batch_size": len(files),
                "succeeded": succeeded,
                "failed": failed,
                "results": batch_results,
            }
            await store_idempotency_response(
                db,
                user_id=current_user.id,
                org_id=org_id,
                route="POST /api/v1/uploads/batch",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_body=final_result,
                status_code=status.HTTP_200_OK,
            )
            return final_result
        finally:
            for item in temp_uploads:
                temp_path = item.get("temp_path")
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

    results: list[dict] = []
    succeeded = 0
    failed = 0

    for file in files:
        filename = file.filename or ""
        temp_path = None
        try:
            if "." not in filename:
                raise ValueError("Nom de fichier invalide (pas d'extension)")

            extension = filename.rsplit(".", 1)[1].lower()
            if extension not in settings.ALLOWED_EXTENSIONS:
                raise ValueError(f"Extension .{extension} non autorisée")

            # Stream to temp file
            temp_fd, temp_path = tempfile.mkstemp(suffix=f".{extension}")
            sha256_hash = hashlib.sha256()
            size = 0

            with os.fdopen(temp_fd, "wb") as tmp:
                while chunk := await file.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > settings.max_upload_size_bytes:
                        raise ValueError(
                            f"Fichier trop volumineux. Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB"
                        )
                    tmp.write(chunk)
                    sha256_hash.update(chunk)

            if size == 0:
                raise ValueError("Fichier vide")

            # SEC-014: Sandbox antivirus / MIME verification
            try:
                scan_file_for_malware(temp_path, extension)
            except SandboxError as scan_err:
                raise ValueError(f"Fichier rejeté : {str(scan_err)}") from scan_err

            result = await _upload_document_body(
                db=db,
                current_user=current_user,
                file=file,
                file_path=Path(temp_path),
                filename=filename,
                extension=extension,
                size=size,
                sha256=sha256_hash.hexdigest(),
                auto_anonymize=auto_anonymize,
                profile=profile,
                document_type=document_type,
                client_name=client_name,
                exercice=exercice,
                doc_category=doc_category,
                background_tasks=background_tasks,
                org_id_override=org_id,
            )
            results.append(result)
            succeeded += 1

        except Exception as exc:
            with contextlib.suppress(Exception):
                await db.rollback()
            logger.warning("batch_upload_file_failed", filename=filename, error=str(exc))
            results.append({
                "status": "error",
                "original_filename": filename,
                "error": str(exc)[:500],
            })
            failed += 1
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    logger.info(
        "batch_upload_complete",
        user_id=str(current_user.id),
        total=len(files),
        succeeded=succeeded,
        failed=failed,
    )

    return {
        "batch_size": len(files),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
