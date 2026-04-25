# memory.md

## 2026-04-23

### Architecture understanding
- Backend is cleanly layered: API → services → models → schemas
- Document domain is central and split into CRUD / processing / export / stats modules
- Async-first design (FastAPI + SQLAlchemy async)
- Background processing can be Celery OR inline fallback

### Key invariants learned
- Upload is streaming-based (avoid memory load)
- `client_name` is mandatory business field
- Storage abstraction must be respected (local / minio / db)
- Privacy-first: anonymization BEFORE AI usage
- Auditability is as important as functionality
- Production config is intentionally strict and must not be weakened

### Risks to avoid
- Breaking document lifecycle (upload → anonymize → validate → export)
- Losing provenance / quality / audit fields
- Returning raw sensitive data in outputs
- Blocking async flow with sync code
- Introducing large memory usage in OCR or file handling

### AI-specific constraints
- Copilot answers must include citations
- Low confidence must trigger warnings
- AI must operate on anonymized text
- Fallback behavior must remain safe

### Testing habits
- Unit tests for config and services are critical
- Upload and document API tests are key integration points
- Golden sets are important for extraction regression

### Future improvements to consider
- Better memory between agents via structured logs
- More explicit service boundaries for extraction vs anonymization
- Improved observability on routing/extractor decisions
- Scaling Celery vs inline processing logic

### Current mental model
ConfiDoc is not just an OCR/anonymizer:
It is a **regulated data pipeline with proof, audit, and safe AI usage constraints**.

All changes should preserve:
1. data safety
2. auditability
3. deterministic outputs where possible
4. controlled AI behavior
