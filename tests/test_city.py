"""
tests/test_city.py – Unit tests cho 6 City Insights endpoints.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_ranked(rank: int) -> dict:
    return {
        "id": rank, "ten_quan": f"Quán Test {rank}", "ten_mon": "Phở",
        "dia_chi": "123 Test", "quan": "Quận 1", "thanh_pho": "ha_noi",
        "gia_min": 50000, "gia_max": 80000, "note": "",
        "so_lan_click": (11 - rank) * 10, "rank": rank,
    }


RANKED_ITEMS   = [_make_ranked(i) for i in range(1, 4)]
DISTRICT_DATA  = [{"quan": "Quận 1", "total": 50}, {"quan": "Quận 3", "total": 30}]
PRICE_DATA     = {"under_50k": 10, "mid_range": 40, "premium": 20, "avg_price": 95000.0, "total": 70}
CATEGORY_DATA  = [{"loai_hinh": "Quán ăn", "total": 50, "percentage": 71.4},
                  {"loai_hinh": "Cafe",    "total": 20, "percentage": 28.6}]


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_search():
    """Patch singleton _search trong deps."""
    with patch("api.deps._search") as m:
        m.top_clicks        = AsyncMock(return_value=RANKED_ITEMS)
        m.district_stats    = AsyncMock(return_value=DISTRICT_DATA)
        m.price_distribution= AsyncMock(return_value=PRICE_DATA)
        m.category_stats    = AsyncMock(return_value=CATEGORY_DATA)
        m.trending          = AsyncMock(return_value=RANKED_ITEMS)
        m.random_discovery  = AsyncMock(return_value=[])
        m.get_all_cities    = MagicMock(return_value=["ha_noi", "ho_chi_minh"])
        # preload_all cần thiết cho lifespan
        m.preload_all       = MagicMock()
        yield m


@pytest.fixture
def client(mock_search):
    from api.main import app
    return TestClient(app)


# ── Tests: /city/{city}/top-clicks ────────────────────────────────────────────

class TestTopClicks:
    def test_returns_list(self, client):
        r = client.get("/city/ha_noi/top-clicks")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert body[0]["rank"] == 1
        assert "so_lan_click" in body[0]

    def test_limit_respected(self, client, mock_search):
        mock_search.top_clicks = AsyncMock(return_value=[_make_ranked(1)])
        r = client.get("/city/ha_noi/top-clicks?limit=1")
        assert r.status_code == 200
        mock_search.top_clicks.assert_called_once_with("ha_noi", 1)

    def test_invalid_city(self, client, mock_search):
        mock_search.top_clicks.side_effect = ValueError("Unknown city: xyz")
        r = client.get("/city/xyz/top-clicks")
        assert r.status_code == 400


# ── Tests: /city/{city}/districts ─────────────────────────────────────────────

class TestDistrictStats:
    def test_returns_districts_response(self, client):
        r = client.get("/city/ha_noi/districts")
        assert r.status_code == 200
        body = r.json()
        assert body["city"] == "ha_noi"
        assert "districts" in body
        assert "total_places" in body
        assert body["total_places"] == 80   # 50 + 30

    def test_district_fields(self, client):
        r = client.get("/city/ha_noi/districts")
        first = r.json()["districts"][0]
        assert "quan" in first
        assert "total" in first

    def test_invalid_city(self, client, mock_search):
        mock_search.district_stats.side_effect = ValueError("Unknown city: bad")
        r = client.get("/city/bad/districts")
        assert r.status_code == 400


# ── Tests: /city/{city}/price-range ───────────────────────────────────────────

class TestPriceDistribution:
    def test_returns_price_fields(self, client):
        r = client.get("/city/ha_noi/price-range")
        assert r.status_code == 200
        body = r.json()
        assert body["city"] == "ha_noi"
        for field in ("under_50k", "mid_range", "premium", "avg_price", "total"):
            assert field in body

    def test_values_match_mock(self, client):
        r = client.get("/city/ha_noi/price-range")
        body = r.json()
        assert body["under_50k"] == 10
        assert body["premium"]   == 20
        assert body["avg_price"] == 95000.0


# ── Tests: /city/{city}/categories ────────────────────────────────────────────

class TestCategoryStats:
    def test_returns_categories(self, client):
        r = client.get("/city/ha_noi/categories")
        assert r.status_code == 200
        body = r.json()
        assert "categories" in body
        assert body["total"] == 70  # 50 + 20

    def test_percentage_field(self, client):
        r = client.get("/city/ha_noi/categories")
        first = r.json()["categories"][0]
        assert "percentage" in first


# ── Tests: /city/{city}/trending ──────────────────────────────────────────────

class TestTrending:
    def test_returns_ranked_list(self, client):
        r = client.get("/city/ha_noi/trending")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        if body:
            assert "rank" in body[0]
            assert "so_lan_click" in body[0]

    def test_limit_param(self, client, mock_search):
        mock_search.trending = AsyncMock(return_value=[_make_ranked(1)])
        r = client.get("/city/ha_noi/trending?limit=5")
        assert r.status_code == 200
        mock_search.trending.assert_called_once_with("ha_noi", 5)


# ── Tests: /city/{city}/random ────────────────────────────────────────────────

class TestRandomDiscovery:
    def test_basic_random(self, client):
        r = client.get("/city/ha_noi/random")
        assert r.status_code == 200
        body = r.json()
        assert "city" in body
        assert "items" in body
        assert "filters_applied" in body

    def test_with_filters(self, client, mock_search):
        r = client.get("/city/ha_noi/random?district=Quận+1&max_price=100000")
        assert r.status_code == 200
        body = r.json()
        assert body["filters_applied"].get("district") == "Quận 1"
        assert body["filters_applied"].get("max_price") == 100000
        mock_search.random_discovery.assert_called_once_with("ha_noi", "Quận 1", 100000, 5)

    def test_no_filters(self, client, mock_search):
        r = client.get("/city/ha_noi/random")
        mock_search.random_discovery.assert_called_once_with("ha_noi", None, None, 5)
