# ==============================================================================
# ConfiDoc Backend — API Dockerfile (Railway root autodetect)
# ==============================================================================
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels ".[processing]" && \
    rm -f /build/wheels/torch-*.whl \
          /build/wheels/torchvision-*.whl \
          /build/wheels/nvidia_*.whl \
          /build/wheels/triton-*.whl \
          /build/wheels/cuda_*.whl \
          /build/wheels/cuda-*.whl

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV DOCLING_DOWNLOAD_MODELS=false
ENV TORCH_HOME=/tmp/torch_cache

WORKDIR /app

# apt-get upgrade applique les correctifs de sécurité OS (gnutls/krb5, etc.)
# présents dans l'image de base au moment du build.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libmagic1 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --upgrade pip "wheel>=0.46.2" && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY . .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN useradd -m confidoc && chown -R confidoc:confidoc /app
USER confidoc

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8000'), timeout=3).read()"

ENTRYPOINT ["/entrypoint.sh"]
