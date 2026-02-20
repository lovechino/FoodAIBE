"""tests/conftest.py – shared fixtures for all tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from api.models import FoodItem


def make_item(**kw) -> FoodItem:
    defaults = dict(
        id=1, ten_quan="Quán Test", ten_mon="Phở", dia_chi="123 Lê Lợi",
        quan="Quận 1", thanh_pho="Hà Nội", gia_min=50000, gia_max=80000, note=""
    )
    defaults.update(kw)
    return FoodItem(**defaults)


@pytest.fixture
def sample_items() -> list[FoodItem]:
    return [
        make_item(id=1, ten_mon="Phở bò", gia_min=50000, gia_max=80000),
        make_item(id=2, ten_mon="Bún chả", ten_quan="Bún Chả Lý", gia_min=40000, gia_max=60000),
        make_item(id=3, ten_mon="Bánh mì", ten_quan="Bánh Mì Hà Nội", gia_min=20000, gia_max=30000),
    ]


@pytest.fixture
def mock_search_fn(sample_items):
    """Async mock search function trả về sample_items."""
    async def _fn(keyword: str, limit: int = 10):
        return sample_items[:limit]
    return _fn


@pytest.fixture
def mock_empty_search_fn():
    async def _fn(keyword: str, limit: int = 10):
        return []
    return _fn
