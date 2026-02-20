"""
models.py – Pydantic schemas cho request/response.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


# ── Request Models ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Câu hỏi của user")
    city: str = Field(default="ha_noi", description="Thành phố (ha_noi, ho_chi_minh, ...)")
    history: Optional[List[dict]] = Field(default=[], description="Lịch sử chat [{'role':'user','text':'...'}]")
    user_address: Optional[str] = Field(default=None, description="Địa chỉ/khu vực của user (text)")


class NearbyRequest(BaseModel):
    query: str = Field(..., description="Loại món/quán muốn tìm")
    city: str = Field(default="ha_noi")
    user_address: str = Field(..., description="Địa chỉ hoặc khu vực của user")


class SearchRequest(BaseModel):
    q: str = Field(..., description="Từ khoá tìm kiếm")
    city: str = Field(default="ha_noi")
    limit: int = Field(default=10, ge=1, le=50)


# ── Response Models ────────────────────────────────────────────────────────────

class FoodItem(BaseModel):
    id: int
    ten_quan: str
    ten_mon: str
    dia_chi: str
    quan: str
    thanh_pho: str
    gia_min: int
    gia_max: int
    note: Optional[str] = ""

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    reply: str
    model_used: Literal["local", "gemini-flash", "gemini-pro"]
    query_type: Literal["simple", "complex", "heavy"]
    results: Optional[List[FoodItem]] = []


class SearchResponse(BaseModel):
    items: list[FoodItem]
    total: int
    city: str


class ClickRequest(BaseModel):
    id: int   = Field(..., description="ID của quán trong bảng food")
    city: str = Field(default="ha_noi", description="Thành phố chứa quán")


class ClickResponse(BaseModel):
    id: int
    city: str
    so_lan_click: int = Field(description="Giá trị so_lan_click sau khi tăng")


class SuggestResponse(BaseModel):
    meal_time: str           # "Bữa sáng", "Bữa trưa", ...
    suggestions: List[FoodItem]
    reply: str               # Câu trả lời tự nhiên từ AI
    model_used: str


class NearbyResponse(BaseModel):
    reply: str
    results: List[FoodItem]
    model_used: str


# ── City Insights Models ───────────────────────────────────────────────────────

class FoodItemRanked(FoodItem):
    """FoodItem mở rộng thêm rank + lượt click, dùng cho top-clicks & trending."""
    so_lan_click: int = Field(default=0, description="Tổng lượt click")
    rank: int         = Field(description="Thứ hạng (1-based)")


class DistrictStat(BaseModel):
    quan: str
    total: int


class DistrictStatsResponse(BaseModel):
    city: str
    districts: List[DistrictStat]
    total_places: int


class PriceDistResponse(BaseModel):
    city: str
    under_50k:  int = Field(description="Số quán giá dưới 50k")
    mid_range:  int = Field(description="Số quán giá 50k–150k")
    premium:    int = Field(description="Số quán giá trên 150k")
    avg_price:  float = Field(description="Giá trung bình (VNĐ)")
    total:      int


class CategoryStat(BaseModel):
    loai_hinh:  str
    total:      int
    percentage: float = Field(description="Phần trăm trong toàn thành phố")


class CategoryStatsResponse(BaseModel):
    city: str
    categories: List[CategoryStat]
    total: int


class RandomDiscoveryResponse(BaseModel):
    city: str
    items: List[FoodItem]
    filters_applied: dict
