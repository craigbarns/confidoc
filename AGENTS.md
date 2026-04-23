# AGENTS.md

## Project identity
ConfiDoc is a privacy-first document processing backend for regulated professions. The core value proposition is: ingest sensitive accounting/legal documents, extract useful business data, pseudonymize or strongly anonymize them, preserve auditability, and expose safe downstream outputs for review, export, and AI-assisted analysis.

Primary domain concerns:
- RGPD / privacy by design
- pseudonymization vs strong anonymization
- auditability and integrity proofs
- human validation before sensitive business use
- safe AI usage only on anonymized data

## Current stack
- Python 3.11+
- FastAPI
- async SQLAlchemy 2.0 + asyncpg
- Alembic
- Redis
- Celery
- PostgreSQL 16
- Storage backends: local / MinIO / database fallback
- Optional AI/OCR integrations: Mistral, Ollama, Tesseract, PyMuPDF, Presidio, LangGraph, pgvector
- Tests: pytest, pytest-asyncio, golden sets

## Architecture rules
- Keep route handlers thin.
- Put business logic in `app/services/*`.
- Keep schemas in `app/schemas/*` and DB models in `app/models/*`.
- Reuse shared helpers before introducing new service variants.
- Prefer adding small focused modules over growing god-files.
- Preserve current split of document routes across:
  - `_doc_shared.py`
  - `_doc_crud.py`
  - `_doc_processing.py`
  - `_doc_export.py`
  - `_doc_stats.py`
- Respect router inclusion order when static routes coexist with `/{document_id}` dynamic routes.

## Coding conventions
- Use type hints everywhere.
- Keep compatibility with strict mypy settings.
- Prefer explicit, readable code over clever abstractions.
- Preserve structured logging patterns using `get_logger()`.
- Raise project HTTP helpers (`http_400`, `http_404`, etc.) where existing code does so.
- Avoid introducing sync DB access in async flows.
- Do not bypass settings from `app.config.Settings`.
- Reuse `get_settings()` instead of ad hoc env access.

## Safety and product invariants
- Never expose raw sensitive text in endpoints intended for audit/compliance exports.
- Default to human review when confidence is limited.
- Any new AI feature must operate on anonymized text unless there is an explicit documented exception.
- Do not weaken production safety guards in `app/config.py`.
- Do not make `STORAGE_BACKEND=local` acceptable in production.
- Respect retention and purge logic; do not silently remove retention hooks.
- Keep request tracing, security headers, and rate limiting intact.

## Upload and storage invariants
- Uploads are streamed to temp files to avoid OOM.
- `client_name` is mandatory in upload flows.
- Allowed extensions and max size must come from settings.
- Malware / sandbox scanning must stay in the upload path.
- `store_file()` / `store_bytes()` are the canonical storage entry points.
- Database storage is fallback-compatible; avoid large in-memory regressions.

## Document workflow invariants
Expected high-level flow:
1. authenticated upload
2. optional auto-processing/anonymization
3. preview
4. validation / approval
5. export / audit / proof / structured dataset
6. AI/copilot only on anonymized content

When changing document processing:
- preserve version semantics (`PREVIEW_ANONYMIZED`, `FINAL_ANONYMIZED`, etc.)
- preserve the distinction between routing, extraction, anonymization, validation, and export
- preserve provenance / quality metadata whenever possible

## OCR / extraction guidance
- OCR and extraction are quality-sensitive and regression-prone.
- Prefer extending extractors and registries rather than adding hard-coded special cases in routes.
- Preserve `quality`, `experience`, and `provenance` payloads when touching structured extraction.
- If a new document type is added, ensure routing confidence, extractor identity, and regression fixtures are considered.

## Copilot / AI guidance
- Copilot answers must remain citation-based and conservative.
- Low confidence should produce warnings, not overconfident language.
- Comparison flows must continue to require anonymized text on both sides.
- Any summarization fallback should remain safe and privacy-preserving.

## Testing expectations
Before merging meaningful changes, run the smallest relevant subset first, then expand:
- `pytest tests/unit/test_config.py -q`
- `pytest tests/api/test_uploads.py -q`
- `pytest tests/api/test_leads.py -q`
- full targeted test package if touching shared infra

For document extraction changes, also consider:
- golden set validation
- smoke scripts in `scripts/`
- readiness / health behavior if infra is touched

## When modifying config or infra
- Keep aliases and parsing behavior in `Settings` backward compatible when reasonable.
- Add tests for new config fields, validators, or production guards.
- Be careful with Railway assumptions: local storage is ephemeral in production.

## Preferred way of working
When implementing a change:
1. read the existing route/service/tests around the feature
2. preserve architecture and invariants
3. make the smallest coherent change
4. add or update tests
5. mention risks if touching privacy, retention, OCR, extraction, or auth

## Avoid
- giant rewrites without necessity
- leaking sensitive text in logs or exports
- moving business logic into routers
- bypassing audit/provenance metadata
- weakening production config validation
- returning overconfident AI outputs without warnings/citations
