"""
search_service.py – FAISS semantic search + SQLite full-text search.
Indexes được load vào RAM khi startup, cache theo từng thành phố.
"""
import os
import sqlite3
import asyncio
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from .models import FoodItem

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
MAX_RESULTS = int(os.getenv("MAX_FAISS_RESULTS", "20"))

VALID_CITIES = {"ha_noi", "ho_chi_minh", "da_nang", "hai_phong", "ha_long", "thanh_hoa"}

# ── Model (singleton) ─────────────────────────────────────────────────────────

_embed_model: Optional[SentenceTransformer] = None

def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        logger.info("Loading embedding model: multilingual-e5-small …")
        _embed_model = SentenceTransformer("intfloat/multilingual-e5-small")
        logger.info("Embedding model loaded.")
    return _embed_model


# ── FAISS index cache ─────────────────────────────────────────────────────────

_faiss_cache: dict[str, faiss.Index] = {}

def _load_faiss(city: str) -> faiss.Index:
    if city not in _faiss_cache:
        idx_path = DATA_DIR / city / "index.faiss"
        if not idx_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {idx_path}")
        logger.info(f"Loading FAISS index for {city} …")
        _faiss_cache[city] = faiss.read_index(str(idx_path))
        logger.info(f"FAISS index {city} loaded ({_faiss_cache[city].ntotal} vectors).")
    return _faiss_cache[city]


# ── SQLite helpers ────────────────────────────────────────────────────────────

def _db_path(city: str) -> str:
    return str(DATA_DIR / city / "food.db")

def _row_to_food(row: sqlite3.Row) -> FoodItem:
    return FoodItem(
        id=row["id"],
        ten_quan=row["ten_quan"] or "",
        ten_mon=row["ten_mon"] or "",
        dia_chi=row["dia_chi"] or "",
        quan=row["quan"] or "",
        thanh_pho=row["thanh_pho"] or "",
        gia_min=row["gia_min"] or 0,
        gia_max=row["gia_max"] or 0,
        note=row["note"] or "",
    )

def _fetch_by_ids(city: str, ids: list[int]) -> list[FoodItem]:
    if not ids:
        return []
    path = _db_path(city)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT * FROM food WHERE id IN ({placeholders})", ids).fetchall()
    conn.close()
    # Giữ đúng thứ tự relevance từ FAISS
    row_map = {r["id"]: _row_to_food(r) for r in rows}
    return [row_map[i] for i in ids if i in row_map]

def _fetch_by_name(city: str, keyword: str, limit: int = 10) -> list[FoodItem]:
    like = f"%{keyword}%"
    path = _db_path(city)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT * FROM food
            WHERE ten_quan LIKE ? OR ten_mon LIKE ?
            ORDER BY so_lan_click DESC
            LIMIT ?""",
        (like, like, limit),
    ).fetchall()
    conn.close()
    return [_row_to_food(r) for r in rows]


# ── Public search functions ───────────────────────────────────────────────────

async def semantic_search(city: str, query: str, top_k: int = 10) -> list[FoodItem]:
    """
    Semantic search bằng FAISS.
    Chạy blocking I/O trong thread pool để không block event loop.
    """
    if city not in VALID_CITIES:
        raise ValueError(f"Unknown city: {city}")

    def _run():
        model = get_embed_model()
        index = _load_faiss(city)

        # multilingual-e5 cần prefix "query: "
        vec = model.encode(f"query: {query}", normalize_embeddings=True)
        vec = np.array([vec], dtype=np.float32)

        actual_k = min(top_k, index.ntotal)
        distances, indices = index.search(vec, actual_k)

        # FAISS indices là 0-based → DB id là 1-based
        ids = [int(i) + 1 for i in indices[0] if i >= 0]
        return _fetch_by_ids(city, ids)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run)


async def text_search(city: str, keyword: str, limit: int = 10) -> list[FoodItem]:
    """SQLite LIKE search – nhanh, dùng cho simple queries."""
    if city not in VALID_CITIES:
        raise ValueError(f"Unknown city: {city}")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_by_name, city, keyword, limit)


async def hybrid_search(city: str, query: str, top_k: int = 10) -> list[FoodItem]:
    """
    Kết hợp semantic + text search, dedup theo id.
    Ưu tiên text match (exact) trước, sau đó semantic.
    """
    sem, txt = await asyncio.gather(
        semantic_search(city, query, top_k),
        text_search(city, query, top_k // 2),
    )
    seen: set[int] = set()
    merged: list[FoodItem] = []
    for item in [*txt, *sem]:          # text kết quả ưu tiên
        if item.id not in seen:
            seen.add(item.id)
            merged.append(item)
    return merged[:top_k]


def get_all_cities() -> list[str]:
    """Liệt kê các city pack đang có."""
    if not DATA_DIR.exists():
        return []
    return [d.name for d in DATA_DIR.iterdir() if d.is_dir() and (d / "food.db").exists()]


def preload_all(cities: list[str] | None = None) -> None:
    """Load tất cả FAISS indexes vào RAM khi startup."""
    target = cities or get_all_cities()
    for city in target:
        try:
            get_embed_model()   # model load 1 lần
            _load_faiss(city)
        except Exception as e:
            logger.warning(f"Could not preload {city}: {e}")
