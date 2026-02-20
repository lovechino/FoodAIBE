"""
core/search.py – SearchService class.
Trách nhiệm: tìm kiếm (FAISS semantic + SQLAlchemy ORM text).

Tất cả I/O SQLite đi qua SQLAlchemy Session (không còn raw sqlite3).
Blocking calls được wrap trong run_in_executor để không block event loop.
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from sqlalchemy import func, case, text
from sqlalchemy.orm import Session

from ..db.models import Food
from ..db.session import db_session
from ..models import FoodItem

logger = logging.getLogger(__name__)

VALID_CITIES = {"ha_noi", "ho_chi_minh", "da_nang", "hai_phong", "ha_long", "thanh_hoa"}


class SearchService:
    """Hybrid search: ưu tiên text match (BR5), bổ sung semantic FAISS.
    Dùng SQLAlchemy ORM – không có raw SQL f-string.
    """

    def __init__(self, data_dir: str | Path, model_name: str = "intfloat/multilingual-e5-small") -> None:
        self._data_dir   = Path(data_dir)
        self._model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._faiss_cache: dict[str, faiss.Index] = {}

    # ── Public: Search ─────────────────────────────────────────────────────────

    async def text_search(self, city: str, keyword: str, limit: int = 10) -> list[FoodItem]:
        """SQLAlchemy LIKE search – fast, no AI needed."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_by_name, city, keyword, limit
        )

    async def semantic_search(self, city: str, query: str, top_k: int = 10) -> list[FoodItem]:
        """FAISS vector search với multilingual-e5 embedding."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._run_faiss, city, query, top_k
        )

    async def hybrid_search(self, city: str, query: str, top_k: int = 10) -> list[FoodItem]:
        """Kết hợp text + semantic, dedup, text match ưu tiên (BR5)."""
        self._validate_city(city)
        sem, txt = await asyncio.gather(
            self.semantic_search(city, query, top_k),
            self.text_search(city, query, top_k // 2),
        )
        return self._merge(txt, sem, top_k)

    # ── Public: Click ──────────────────────────────────────────────────────────

    async def increment_click(self, city: str, food_id: int) -> int:
        """Tăng so_lan_click +1 cho quán food_id. Trả về giá trị mới."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._do_increment, city, food_id
        )

    def _do_increment(self, city: str, food_id: int) -> int:
        with db_session(city, self._data_dir) as session:
            food = session.get(Food, food_id)
            if food is None:
                raise ValueError(f"Food id={food_id} not found in {city}")
            food.so_lan_click = (food.so_lan_click or 0) + 1
            session.flush()
            return food.so_lan_click

    # ── Public: City Insights ──────────────────────────────────────────────────

    async def top_clicks(self, city: str, limit: int = 10) -> list[dict]:
        """Top `limit` quán được click nhiều nhất."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_top_clicks, city, limit
        )

    async def district_stats(self, city: str) -> list[dict]:
        """Thống kê số lượng quán theo từng quận."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_district_stats, city
        )

    async def price_distribution(self, city: str) -> dict:
        """Phân bố giá 3 phân khúc: dưới 50k / 50k-150k / trên 150k."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_price_dist, city
        )

    async def category_stats(self, city: str) -> list[dict]:
        """Cơ cấu loại hình quán ăn theo thành phố."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_category_stats, city
        )

    async def trending(self, city: str, limit: int = 10) -> list[dict]:
        """Top trending dựa trên so_lan_click (có rank)."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_trending, city, limit
        )

    async def random_discovery(
        self, city: str,
        district: str | None = None,
        max_price: int | None = None,
        limit: int = 5,
    ) -> list[FoodItem]:
        """Random discovery có filter quận và giá."""
        self._validate_city(city)
        return await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_random, city, district, max_price, limit
        )

    # ── Public: System ─────────────────────────────────────────────────────────

    def preload_all(self) -> None:
        """Load tất cả FAISS indexes vào RAM khi startup (BR6)."""
        for city in self.get_all_cities():
            try:
                self._get_model()
                self._load_faiss(city)
                logger.info(f"Preloaded: {city}")
            except Exception as e:
                logger.warning(f"Could not preload {city}: {e}")

    def get_all_cities(self) -> list[str]:
        if not self._data_dir.exists():
            return []
        return [d.name for d in self._data_dir.iterdir() if d.is_dir() and (d / "food.db").exists()]

    # ── Private: FAISS ─────────────────────────────────────────────────────────

    def _run_faiss(self, city: str, query: str, top_k: int) -> list[FoodItem]:
        model = self._get_model()
        index = self._load_faiss(city)
        vec   = model.encode(f"query: {query}", normalize_embeddings=True)
        k     = min(top_k, index.ntotal)
        _, indices = index.search(np.array([vec], dtype=np.float32), k)
        ids = [int(i) + 1 for i in indices[0] if i >= 0]
        return self._fetch_by_ids(city, ids)

    def _load_faiss(self, city: str) -> faiss.Index:
        if city not in self._faiss_cache:
            path = self._data_dir / city / "index.faiss"
            if not path.exists():
                raise FileNotFoundError(f"FAISS not found: {path}")
            self._faiss_cache[city] = faiss.read_index(str(path))
        return self._faiss_cache[city]

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("Loading embedding model…")
            self._model = SentenceTransformer(self._model_name)
        return self._model

    # ── Private: ORM helpers ───────────────────────────────────────────────────

    def _fetch_by_ids(self, city: str, ids: list[int]) -> list[FoodItem]:
        """Lấy foods theo list id, giữ đúng thứ tự relevance từ FAISS."""
        if not ids:
            return []
        with db_session(city, self._data_dir) as session:
            rows = session.query(Food).filter(Food.id.in_(ids)).all()
        row_map = {r.id: self._orm_to_item(r) for r in rows}
        return [row_map[i] for i in ids if i in row_map]

    def _fetch_by_name(self, city: str, keyword: str, limit: int) -> list[FoodItem]:
        """LIKE search trên ten_quan + ten_mon, ưu tiên click cao."""
        like = f"%{keyword}%"
        with db_session(city, self._data_dir) as session:
            rows = (
                session.query(Food)
                .filter(Food.ten_quan.ilike(like) | Food.ten_mon.ilike(like))
                .order_by(Food.so_lan_click.desc())
                .limit(limit)
                .all()
            )
        return [self._orm_to_item(r) for r in rows]

    # ── Private: City Insights ORM ─────────────────────────────────────────────

    def _fetch_top_clicks(self, city: str, limit: int) -> list[dict]:
        with db_session(city, self._data_dir) as session:
            rows = (
                session.query(Food)
                .order_by(Food.so_lan_click.desc())
                .limit(limit)
                .all()
            )
        return [
            {**self._orm_to_item(r).model_dump(), "so_lan_click": r.so_lan_click or 0, "rank": rank}
            for rank, r in enumerate(rows, start=1)
        ]

    def _fetch_district_stats(self, city: str) -> list[dict]:
        with db_session(city, self._data_dir) as session:
            rows = (
                session.query(
                    func.coalesce(func.nullif(func.trim(Food.quan), ""), "Chưa phân loại").label("quan"),
                    func.count().label("total"),
                )
                .group_by(Food.quan)
                .order_by(func.count().desc())
                .all()
            )
        return [{"quan": r.quan, "total": r.total} for r in rows]

    def _fetch_price_dist(self, city: str) -> dict:
        with db_session(city, self._data_dir) as session:
            row = session.query(
                func.sum(case((Food.gia_min < 50_000, 1), else_=0)).label("under_50k"),
                func.sum(case(((Food.gia_min >= 50_000) & (Food.gia_min <= 150_000), 1), else_=0)).label("mid_range"),
                func.sum(case((Food.gia_min > 150_000, 1), else_=0)).label("premium"),
                func.round(
                    func.avg(case((Food.gia_min > 0, Food.gia_min), else_=Food.gia_max)), 0
                ).label("avg_price"),
                func.count().label("total"),
            ).one()
        return {
            "under_50k": row.under_50k or 0,
            "mid_range":  row.mid_range  or 0,
            "premium":    row.premium    or 0,
            "avg_price":  float(row.avg_price or 0),
            "total":      row.total      or 0,
        }

    def _fetch_category_stats(self, city: str) -> list[dict]:
        """Phân loại theo khoảng giá (DB không có cột loai_hinh)."""
        with db_session(city, self._data_dir) as session:
            total = session.query(func.count(Food.id)).scalar() or 1

            buckets = [
                ("Bình dân (< 50k)",       Food.gia_min < 50_000),
                ("Tầm trung (50k–150k)",   (Food.gia_min >= 50_000) & (Food.gia_min <= 150_000)),
                ("Cao cấp (> 150k)",       Food.gia_min > 150_000),
                ("Chưa có giá",            Food.gia_min == 0),
            ]
            result = []
            for label, condition in buckets:
                count = session.query(func.count(Food.id)).filter(condition).scalar() or 0
                result.append({
                    "loai_hinh":  label,
                    "total":      count,
                    "percentage": round(count / total * 100, 1),
                })
        return result

    def _fetch_trending(self, city: str, limit: int) -> list[dict]:
        with db_session(city, self._data_dir) as session:
            rows = (
                session.query(Food)
                .filter(Food.so_lan_click > 0)
                .order_by(Food.so_lan_click.desc())
                .limit(limit)
                .all()
            )
        return [
            {**self._orm_to_item(r).model_dump(), "so_lan_click": r.so_lan_click or 0, "rank": rank}
            for rank, r in enumerate(rows, start=1)
        ]

    def _fetch_random(
        self, city: str,
        district: str | None,
        max_price: int | None,
        limit: int,
    ) -> list[FoodItem]:
        with db_session(city, self._data_dir) as session:
            q = session.query(Food)
            if district:
                like = f"%{district}%"
                q = q.filter(Food.quan.ilike(like) | Food.dia_chi.ilike(like))
            if max_price:
                q = q.filter(
                    (Food.gia_min <= max_price) |
                    ((Food.gia_min == 0) & (Food.gia_max <= max_price))
                )
            rows = q.order_by(func.random()).limit(limit).all()
        return [self._orm_to_item(r) for r in rows]

    # ── Private: Converters ────────────────────────────────────────────────────

    @staticmethod
    def _orm_to_item(food: Food) -> FoodItem:
        return FoodItem(
            id=food.id,
            ten_quan=food.ten_quan or "",
            ten_mon=food.ten_mon   or "",
            dia_chi=food.dia_chi   or "",
            quan=food.quan         or "",
            thanh_pho=food.thanh_pho or "",
            gia_min=food.gia_min   or 0,
            gia_max=food.gia_max   or 0,
            note=food.note         or "",
        )

    @staticmethod
    def _merge(priority: list[FoodItem], secondary: list[FoodItem], top_k: int) -> list[FoodItem]:
        seen: set[int] = set()
        merged: list[FoodItem] = []
        for item in [*priority, *secondary]:
            if item.id not in seen:
                seen.add(item.id)
                merged.append(item)
        return merged[:top_k]

    @staticmethod
    def _validate_city(city: str) -> None:
        if city not in VALID_CITIES:
            raise ValueError(f"Unknown city: {city}")
