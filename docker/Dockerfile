# ==============================================================================
# ConfiDoc Backend — API Dockerfile
# ==============================================================================
FROM python:3.11-slim-bookworm AS builder

# Éviter l'écriture de fichiers .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

# Dépendances système pour PyMuPDF, spaCy, et compils C
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels ".[processing]"


# ==============================================================================
# Phase finale (Allégée)
# ==============================================================================
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Réinstaller libmagic pour python-magic (détection MIME sécurisée)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les wheels pré-construits
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copier le code (sans le .git, via .dockerignore)
COPY . .

# Utilisateur non-root pour la sécurité
RUN useradd -m confidoc && chown -R confidoc:confidoc /app
USER confidoc

# Exposer le port par défaut (Railway utilise $PORT dynamique)
EXPOSE 8000

# Lancer l'API sur le port Railway dynamique (fallback 8000 en local)
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
