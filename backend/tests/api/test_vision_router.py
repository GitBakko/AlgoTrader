# MANTIS-EVOLUTION: Vision Router Tests
"""Tests for /api/vision endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestVisionStatus:
    """Tests for GET /api/vision/status."""

    @pytest.mark.asyncio
    async def test_status_returns_config(self, client):
        """Status endpoint returns vision + RAG config."""
        resp = await client.get("/api/vision/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "vision_enabled" in data["data"]
        assert "rag_enabled" in data["data"]
        assert "vision_model" in data["data"]
        assert "chart_width" in data["data"]
        assert "rag_max_tokens" in data["data"]


class TestChartGeneration:
    """Tests for POST /api/vision/chart."""

    @pytest.mark.asyncio
    async def test_chart_returns_png(self, client):
        """Chart endpoint returns PNG image."""
        resp = await client.post("/api/vision/chart?epic=XAUUSD")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        # Check PNG magic bytes
        assert resp.content[:4] == b"\x89PNG"

    @pytest.mark.asyncio
    async def test_chart_requires_epic(self, client):
        """Chart endpoint requires epic query param."""
        resp = await client.post("/api/vision/chart")
        assert resp.status_code == 422  # validation error


class TestVisionAnalyze:
    """Tests for POST /api/vision/analyze."""

    @pytest.mark.asyncio
    async def test_analyze_disabled_returns_error(self, client):
        """When VISION_ENABLED=false, returns 403 with success=False.

        H1-API fix: `_error(msg, status)` now returns the requested
        status code (was always 200 prior to the audit fix)."""
        with patch("src.api.routers.vision.get_settings") as mock_settings:
            s = MagicMock()
            s.vision_enabled = False
            mock_settings.return_value = s
            resp = await client.post("/api/vision/analyze?epic=XAUUSD")
            assert resp.status_code == 403
            data = resp.json()
            assert data["success"] is False
            assert "disabled" in data["error"].lower()


class TestRAGContext:
    """Tests for GET /api/vision/rag."""

    @pytest.mark.asyncio
    async def test_rag_disabled_returns_error(self, client):
        """When RAG_ENABLED=false, returns 403 with success=False.

        H1-API fix: `_error(msg, status)` now returns the requested
        status code."""
        with patch("src.api.routers.vision.get_settings") as mock_settings:
            s = MagicMock()
            s.rag_enabled = False
            mock_settings.return_value = s
            resp = await client.get("/api/vision/rag?epic=XAUUSD")
            assert resp.status_code == 403
            data = resp.json()
            assert data["success"] is False
            assert "disabled" in data["error"].lower()
