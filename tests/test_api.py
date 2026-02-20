"""
tests/test_api.py – Integration tests via FastAPI TestClient.
Kịch bản: tất cả endpoints trả đúng status + schema.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_services(sample_items):
    """Patch tất cả external calls: FAISS, SQLite, Gemini."""
    with (
        patch("api.deps._search") as m_search,
        patch("api.deps._gemini") as m_gemini,
        patch("api.deps._simple") as m_simple,
        patch("api.deps._router") as m_router,
    ):
        from api.core.router import RouteDecision
        m_router.route.return_value = RouteDecision("local", 256, "simple", "test")
        m_router.get_meal_time.return_value = "Bữa trưa"
        m_search.hybrid_search = AsyncMock(return_value=sample_items)
        m_search.text_search   = AsyncMock(return_value=sample_items)
        m_search.get_all_cities.return_value = ["ha_noi", "ho_chi_minh"]
        m_gemini.chat          = AsyncMock(return_value="Test Gemini reply")
        m_gemini.rank_nearby   = AsyncMock(return_value="Gần nhất: Quán Test")
        m_simple.handle        = AsyncMock(return_value=("Template reply", sample_items, True))
        yield


@pytest.fixture
def client(mock_services):
    from api.main import app
    return TestClient(app)


# ── /health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert "time" in r.json()
        assert "cities" in r.json()


# ── /cities ────────────────────────────────────────────────────────────────────

class TestCities:
    def test_returns_list(self, client):
        r = client.get("/cities")
        assert r.status_code == 200
        assert isinstance(r.json()["cities"], list)


# ── /search ────────────────────────────────────────────────────────────────────

class TestSearch:
    def test_basic_search(self, client):
        r = client.get("/search?q=phở&city=ha_noi")
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert body["city"] == "ha_noi"

    def test_missing_q_param(self, client):
        r = client.get("/search?city=ha_noi")
        assert r.status_code == 422   # validation error


# ── POST /chat ─────────────────────────────────────────────────────────────────

class TestChat:
    def test_simple_chat(self, client):
        r = client.post("/chat", json={"message": "tôi muốn ăn phở", "city": "ha_noi"})
        assert r.status_code == 200
        body = r.json()
        assert "reply" in body
        assert "model_used" in body
        assert "query_type" in body
        assert isinstance(body["results"], list)

    def test_chat_with_history(self, client):
        r = client.post("/chat", json={
            "message": "còn quán nào khác không?",
            "city": "ha_noi",
            "history": [{"role": "user", "text": "tìm quán phở"}, {"role": "model", "text": "Có nhiều quán!"}],
        })
        assert r.status_code == 200

    def test_empty_message_rejected(self, client):
        r = client.post("/chat", json={"message": "", "city": "ha_noi"})
        assert r.status_code == 422

    def test_message_too_long_rejected(self, client):
        r = client.post("/chat", json={"message": "x" * 1001, "city": "ha_noi"})
        assert r.status_code == 422


# ── GET /suggest ───────────────────────────────────────────────────────────────

class TestSuggest:
    def test_suggest_default(self, client):
        r = client.get("/suggest?city=ha_noi")
        assert r.status_code == 200
        body = r.json()
        assert "meal_time" in body
        assert "suggestions" in body
        assert "reply" in body

    def test_suggest_with_hour(self, client):
        r = client.get("/suggest?city=ha_noi&hour=7")
        assert r.status_code == 200


# ── POST /nearby ───────────────────────────────────────────────────────────────

class TestNearby:
    def test_nearby(self, client):
        r = client.post("/nearby", json={
            "query": "phở",
            "city": "ha_noi",
            "user_address": "123 Đinh Tiên Hoàng, Hoàn Kiếm",
        })
        assert r.status_code == 200
        body = r.json()
        assert "reply" in body
        assert "results" in body
        assert "model_used" in body
