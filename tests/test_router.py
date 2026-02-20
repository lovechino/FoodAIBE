"""
tests/test_router.py – Unit tests cho QueryRouter.
Kịch bản test theo BA.md:
  - BR1: simple queries → local
  - BR2: complex queries → gemini-flash
  - BR3: heavy queries → gemini-pro
"""
import pytest
from api.core.router import QueryRouter

@pytest.fixture
def router():
    return QueryRouter()


class TestSimpleRouting:
    """BR1: simple query → local model, $0 cost."""

    @pytest.mark.parametrize("query", [
        "tôi muốn ăn phở",
        "toi muon an pho",
        "cho tôi ăn bún chả",
        "gợi ý món nào ngon",
        "phở giá bao nhiêu",
        "so sánh giá bún chả và phở",
    ])
    def test_simple_routes_to_local(self, router, query):
        result = router.route(query)
        assert result.model == "local", f"Expected local for: {query!r}"
        assert result.query_type == "simple"
        assert result.max_output_tokens == 256


class TestComplexRouting:
    """BR2: complex query → gemini-flash."""

    @pytest.mark.parametrize("query", [
        "tìm quán phở gần tôi",
        "quán nào gần đây mở lúc này",
        "tối nay nên ăn gì",
    ])
    def test_complex_routes_to_flash(self, router, query):
        result = router.route(query)
        assert result.model == "gemini-flash"
        assert result.query_type == "complex"
        assert result.max_output_tokens <= 800

    def test_location_flag_triggers_complex(self, router):
        result = router.route("tìm quán gần", has_location=True)
        assert result.model == "gemini-flash"

    def test_long_query_triggers_complex(self, router):
        result = router.route("a" * 101)
        assert result.model == "gemini-flash"


class TestHeavyRouting:
    """BR3: heavy query → gemini-pro."""

    def test_very_long_query_is_heavy(self, router):
        result = router.route("a" * 201)
        assert result.model == "gemini-pro"
        assert result.query_type == "heavy"

    def test_multi_compare_is_heavy(self, router):
        result = router.route("so sánh bún chả với phở và với cơm tấm")
        assert result.model == "gemini-pro"


class TestMealTime:
    """get_meal_time trả đúng bữa ăn theo giờ."""

    @pytest.mark.parametrize("hour,expected", [
        (6,  "Bữa sáng"),
        (9,  "Bữa sáng"),
        (10, "Bữa trưa"),
        (13, "Bữa trưa"),
        (14, "Xế chiều"),
        (16, "Xế chiều"),
        (17, "Bữa tối"),
        (20, "Bữa tối"),
        (21, "Ăn đêm"),
        (3,  "Ăn đêm"),
    ])
    def test_meal_time_by_hour(self, hour, expected):
        assert QueryRouter.get_meal_time(hour) == expected
