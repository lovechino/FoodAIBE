"""
tests/test_search.py – Unit tests cho SearchService (mock DB).
Kịch bản: validate city, merge logic, row parsing.
"""
import sqlite3
import tempfile
import os
import pytest
from pathlib import Path

import numpy as np


# ── Global: reset engine cache giữa các test ───────────────────────────────────

@pytest.fixture(autouse=True)
def clear_engine_cache():
    """Xóa SQLAlchemy engine cache trước mỗi test để tránh xung đột."""
    from api.db import session as sess_module
    sess_module._engines.clear()
    sess_module._session_factories.clear()
    yield
    sess_module._engines.clear()
    sess_module._session_factories.clear()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_test_db(path: Path) -> None:
    """Tạo SQLite test DB với dữ liệu mẫu."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE food (
          id INTEGER PRIMARY KEY,
          ten_quan TEXT, ten_mon TEXT, dia_chi TEXT,
          quan TEXT, thanh_pho TEXT,
          gia_min INTEGER, gia_max INTEGER,
          note TEXT, so_lan_click INTEGER DEFAULT 0
        )
    """)
    conn.executemany("INSERT INTO food VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (1, "Phở Hà Nội",  "Phở bò",    "123 Đinh Tiên Hoàng", "Hoàn Kiếm", "Hà Nội", 50000, 80000, "", 10),
        (2, "Bún Chả Lý",  "Bún chả",   "45 Hàng Than",        "Ba Đình",   "Hà Nội", 40000, 60000, "", 5),
        (3, "Bánh Mì 25",  "Bánh mì",   "25 Đinh Lễ",          "Hoàn Kiếm", "Hà Nội", 20000, 30000, "", 8),
    ])
    conn.commit()
    conn.close()


@pytest.fixture
def test_data_dir(tmp_path):
    city_dir = tmp_path / "ha_noi"
    city_dir.mkdir()
    _create_test_db(city_dir / "food.db")
    return tmp_path


@pytest.fixture
def search_service(test_data_dir, monkeypatch):
    from api.core.search import SearchService
    svc = SearchService(data_dir=test_data_dir)
    # Patch VALID_CITIES cho test
    monkeypatch.setattr("api.core.search.VALID_CITIES", {"ha_noi"})
    return svc


class TestTextSearch:
    """text_search trả về kết quả khớp."""

    @pytest.mark.asyncio
    async def test_find_by_name(self, search_service):
        results = await search_service.text_search("ha_noi", "Phở")
        assert len(results) >= 1
        assert any("Phở" in r.ten_mon for r in results)

    @pytest.mark.asyncio
    async def test_find_by_shop(self, search_service):
        results = await search_service.text_search("ha_noi", "Bún Chả Lý")
        assert len(results) >= 1
        assert results[0].ten_quan == "Bún Chả Lý"

    @pytest.mark.asyncio
    async def test_empty_result(self, search_service):
        results = await search_service.text_search("ha_noi", "xyz_không_tồn_tại")
        assert results == []

    @pytest.mark.asyncio
    async def test_limit_respected(self, search_service):
        results = await search_service.text_search("ha_noi", "á", limit=2)
        assert len(results) <= 2


class TestValidateCity:
    """_validate_city raise ValueError với city không hợp lệ."""

    @pytest.mark.asyncio
    async def test_invalid_city_raises(self, search_service):
        with pytest.raises(ValueError, match="Unknown city"):
            await search_service.text_search("invalid_city", "phở")


class TestMerge:
    """_merge ưu tiên text match (BR5) và dedup."""

    def test_priority_items_come_first(self):
        from api.core.search import SearchService
        from api.models import FoodItem

        def make(id, name):
            return FoodItem(id=id, ten_quan="Q", ten_mon=name, dia_chi="", quan="", thanh_pho="", gia_min=0, gia_max=0, note="")

        p   = make(1, "Priority")
        s   = make(2, "Secondary")
        dup = make(1, "Duplicate")
        merged = SearchService._merge([p], [dup, s], top_k=10)
        assert merged[0].id == 1
        assert merged[1].id == 2
        assert len(merged) == 2  # dup loại bỏ


class TestRowToItem:
    """_orm_to_item chuyển đúng SQLAlchemy Food object sang FoodItem."""

    def test_row_conversion(self, test_data_dir, monkeypatch):
        from api.core.search import SearchService
        from api.db.models import Food
        from api.db.session import db_session
        monkeypatch.setattr("api.core.search.VALID_CITIES", {"ha_noi"})
        svc = SearchService(data_dir=test_data_dir)
        with db_session("ha_noi", test_data_dir) as session:
            food = session.get(Food, 1)
        item = svc._orm_to_item(food)
        assert item.id == 1
        assert item.ten_mon == "Phở bò"
        assert item.gia_min == 50000


class TestIncrementClick:
    """increment_click tăng so_lan_click đúng trong SQLite."""

    @pytest.mark.asyncio
    async def test_increments_once(self, search_service):
        new_count = await search_service.increment_click("ha_noi", 1)
        assert new_count == 11   # ban đầu là 10

    @pytest.mark.asyncio
    async def test_increments_multiple_times(self, search_service):
        await search_service.increment_click("ha_noi", 2)
        new_count = await search_service.increment_click("ha_noi", 2)
        assert new_count == 7    # ban đầu là 5, +1 +1 = 7

    @pytest.mark.asyncio
    async def test_invalid_id_raises(self, search_service):
        with pytest.raises(ValueError, match="not found"):
            await search_service.increment_click("ha_noi", 99999)

    @pytest.mark.asyncio
    async def test_invalid_city_raises(self, search_service):
        with pytest.raises(ValueError, match="Unknown city"):
            await search_service.increment_click("invalid_city", 1)

    def test_click_persisted_in_db(self, search_service, test_data_dir):
        """Đảm bảo thay đổi được ghi vào file SQLite (không chỉ in-memory)."""
        import asyncio
        asyncio.run(search_service.increment_click("ha_noi", 3))
        conn = sqlite3.connect(str(test_data_dir / "ha_noi" / "food.db"))
        row  = conn.execute("SELECT so_lan_click FROM food WHERE id=3").fetchone()
        conn.close()
        assert row[0] == 9   # ban đầu là 8, +1 = 9
