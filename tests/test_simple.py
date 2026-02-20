"""
tests/test_simple.py – Unit tests cho SimpleQueryHandler.
Kịch bản test theo BA.md UC1, UC2:
  - parse_intent nhận đúng intent và keyword
  - template response đúng format
  - empty results → fallback message
"""
import pytest
from api.core.simple import SimpleQueryHandler


@pytest.fixture
def handler():
    return SimpleQueryHandler()


class TestParseIntent:
    """parse_intent trả về đúng (intent, keyword, keyword2)."""

    # UC1 – want_to_eat
    @pytest.mark.parametrize("query,expected_kw", [
        ("tôi muốn ăn phở",         "phở"),
        ("toi muon an bun cha",      "bun cha"),
        ("cho tôi ăn cơm tấm",      "cơm tấm"),
        ("cho toi an bun",           "bun"),
    ])
    def test_want_to_eat(self, handler, query, expected_kw):
        intent, kw, _ = handler.parse_intent(query)
        assert intent == "want_to_eat"
        assert expected_kw in kw

    # UC2 – price_query
    @pytest.mark.parametrize("query,expected_kw", [
        ("phở giá bao nhiêu",        "phở"),
        ("bún chả bao nhiêu tiền",   "bún"),  # regex captures up to boundary
    ])
    def test_price_query(self, handler, query, expected_kw):
        intent, kw, _ = handler.parse_intent(query)
        assert intent == "price_query"
        assert expected_kw in kw

    # UC2 – price_compare
    def test_price_compare(self, handler):
        intent, kw1, kw2 = handler.parse_intent("so sánh giá phở với bún chả")
        assert intent == "price_compare"
        assert "phở" in kw1
        assert kw2 is not None and len(kw2) > 0   # kw2 captured from 'bún chả'

    # suggest
    def test_suggest(self, handler):
        intent, _, _ = handler.parse_intent("gợi ý món ăn sáng")
        assert intent == "suggest"

    # unknown
    def test_unknown(self, handler):
        intent, _, _ = handler.parse_intent("hello world")
        assert intent == "unknown"


class TestHandleWantToEat:
    """handle() với intent want_to_eat trả về template đúng."""

    @pytest.mark.asyncio
    async def test_returns_handled(self, handler, sample_items, mock_search_fn):
        text, items, handled = await handler.handle("tôi muốn ăn phở", mock_search_fn, hour=12)
        assert handled is True
        assert len(items) > 0
        assert "quán" in text.lower() or "phở" in text.lower()

    @pytest.mark.asyncio
    async def test_empty_results_gives_fallback(self, handler, mock_empty_search_fn):
        text, items, handled = await handler.handle("tôi muốn ăn phở", mock_empty_search_fn, hour=12)
        assert handled is True
        assert items == []
        assert "chưa tìm thấy" in text.lower() or "không" in text.lower()


class TestHandleUnknown:
    """handle() với intent unknown trả về handled=False."""

    @pytest.mark.asyncio
    async def test_unknown_not_handled(self, handler, mock_search_fn):
        _, _, handled = await handler.handle("hello world xyz", mock_search_fn, hour=12)
        assert handled is False


class TestFormatPrice:
    """_fmt helper format giá đúng."""

    @pytest.mark.parametrize("mn,mx,expected", [
        (50000, 80000, "50k–80k"),
        (60000, 60000, "60k"),
        (0, 0, "Chưa có giá"),
        (1, 1, "Chưa có giá"),
    ])
    def test_fmt(self, handler, mn, mx, expected):
        assert handler._fmt(mn, mx) == expected
