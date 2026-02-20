"""routes/city.py – City Insights endpoints.

6 endpoint khai thác đặc trưng của từng thành phố:
  GET /city/{city}/top-clicks    → Top 10 quán được click nhiều nhất
  GET /city/{city}/districts     → Thống kê số quán theo quận
  GET /city/{city}/price-range   → Phân bố giá 3 phân khúc
  GET /city/{city}/categories    → Cơ cấu loại hình quán ăn
  GET /city/{city}/trending      → Trending theo click (quán có ≥1 click)
  GET /city/{city}/random        → Random discovery (có filter quận + giá)
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..deps import get_search
from ..models import (
    DistrictStatsResponse,
    FoodItemRanked,
    PriceDistResponse,
    CategoryStatsResponse,
    RandomDiscoveryResponse,
)

router = APIRouter(prefix="/city", tags=["City Insights"])


# ── 1. Top Clicks ─────────────────────────────────────────────────────────────

@router.get(
    "/{city}/top-clicks",
    response_model=list[FoodItemRanked],
    summary="Top quán được click nhiều nhất",
)
async def top_clicks(
    city:  str,
    limit: int = Query(default=10, ge=1, le=50, description="Số lượng kết quả"),
):
    """
    Trả về danh sách quán sắp xếp theo **so_lan_click giảm dần**.
    Mỗi item có thêm `so_lan_click` và `rank` (1-based).
    """
    try:
        return await get_search().top_clicks(city, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 2. District Stats ─────────────────────────────────────────────────────────

@router.get(
    "/{city}/districts",
    response_model=DistrictStatsResponse,
    summary="Thống kê số quán theo quận",
)
async def district_stats(city: str):
    """
    Phân bố quán ăn theo từng **quận/huyện**, sắp xếp theo số lượng.
    Hữu ích để vẽ bản đồ mật độ ẩm thực.
    """
    try:
        districts = await get_search().district_stats(city)
        total = sum(d["total"] for d in districts)
        return DistrictStatsResponse(city=city, districts=districts, total_places=total)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 3. Price Distribution ─────────────────────────────────────────────────────

@router.get(
    "/{city}/price-range",
    response_model=PriceDistResponse,
    summary="Phân bố giá quán ăn",
)
async def price_distribution(city: str):
    """
    Phân chia quán ăn theo **3 phân khúc giá**:
    - `under_50k`  – Bình dân (< 50.000 VNĐ)
    - `mid_range`  – Tầm trung (50k – 150k)
    - `premium`    – Cao cấp (> 150k)

    Kèm thêm `avg_price` trung bình toàn thành phố.
    """
    try:
        data = await get_search().price_distribution(city)
        return PriceDistResponse(city=city, **data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 4. Category Stats ─────────────────────────────────────────────────────────

@router.get(
    "/{city}/categories",
    response_model=CategoryStatsResponse,
    summary="Cơ cấu loại hình quán ăn",
)
async def category_stats(city: str):
    """
    Thống kê **loại hình** (quán ăn, nhà hàng, cafe, ...) và tỷ lệ phần trăm.
    """
    try:
        cats = await get_search().category_stats(city)
        total = sum(c["total"] for c in cats)
        return CategoryStatsResponse(city=city, categories=cats, total=total)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 5. Trending ───────────────────────────────────────────────────────────────

@router.get(
    "/{city}/trending",
    response_model=list[FoodItemRanked],
    summary="Top trending theo lượt click",
)
async def trending(
    city:  str,
    limit: int = Query(default=10, ge=1, le=50),
):
    """
    Quán trending = **click nhiều + đã từng được tương tác** (so_lan_click > 0).
    Phân biệt với top-clicks: trending loại bỏ quán chưa có lượt click nào.
    """
    try:
        return await get_search().trending(city, limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 6. Random Discovery ───────────────────────────────────────────────────────

@router.get(
    "/{city}/random",
    response_model=RandomDiscoveryResponse,
    summary="Khám phá ngẫu nhiên",
)
async def random_discovery(
    city:      str,
    district:  Optional[str] = Query(default=None, description="Lọc theo quận (tên một phần)"),
    max_price: Optional[int] = Query(default=None, ge=0, description="Giá tối đa (VNĐ)"),
    limit:     int           = Query(default=5, ge=1, le=20),
):
    """
    Gợi ý **ngẫu nhiên** – mỗi lần gọi cho kết quả khác nhau.
    Hỗ trợ filter thêm theo quận (`district`) và giá tối đa (`max_price`).
    """
    try:
        items = await get_search().random_discovery(city, district, max_price, limit)
        filters: dict = {}
        if district:
            filters["district"] = district
        if max_price:
            filters["max_price"] = max_price
        return RandomDiscoveryResponse(city=city, items=items, filters_applied=filters)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
