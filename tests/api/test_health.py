"""ConfiDoc — Tests health / readiness / metrics endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    """Le health check doit retourner 200 et status healthy."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "confidoc-backend"


@pytest.mark.anyio
async def test_health_response_structure(client: AsyncClient):
    """Le health check retourne la structure attendue."""
    response = await client.get("/health")
    data = response.json()
    assert "status" in data
    assert "service" in data


@pytest.mark.anyio
async def test_readiness_endpoint_responds_with_known_shape(client: AsyncClient):
    """/readiness doit toujours répondre (200 si OK, 503 si une dépendance KO).

    Quel que soit l'environnement de test, la route doit exister, renvoyer
    un JSON avec ``service``, ``status`` et un dict ``checks`` qui inclut
    au moins ``database`` et ``redis``. C'est la sonde que Railway utilise
    pour redémarrer le service ; un 404 ici casserait le déploiement.
    """
    response = await client.get("/readiness")
    assert response.status_code in (200, 503)
    body = response.json()
    assert body["service"] == "confidoc-backend"
    assert body["status"] in ("ready", "degraded")
    checks = body.get("checks", {})
    assert "database" in checks
    assert "redis" in checks


@pytest.mark.anyio
async def test_metrics_endpoint_exposes_prometheus_payload(client: AsyncClient):
    """/metrics doit servir un payload Prometheus en text/plain.

    ``prometheus_client`` is a runtime dependency. If the test environment
    is missing it (e.g. an old image rebuild), we skip rather than
    pretend the route is broken.
    """
    pytest.importorskip("prometheus_client")
    response = await client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/plain")


@pytest.mark.anyio
async def test_root_path_serves_landing(client: AsyncClient):
    """GET / ne doit jamais être un 404 (landing publique)."""
    response = await client.get("/")
    assert response.status_code == 200
