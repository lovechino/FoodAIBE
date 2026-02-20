"""
router_model.py – Phân loại query và chọn model AI phù hợp.
Simple  → template ($0)
Complex → Gemini Flash (rẻ)
Heavy   → Gemini Pro (khi cần)
"""
import re
from dataclasses import dataclass
from typing import Literal

ModelTier = Literal["local", "gemini-flash", "gemini-pro"]
QueryType = Literal["simple", "complex", "heavy"]


@dataclass
class RouteDecision:
    model: ModelTier
    max_output_tokens: int
    query_type: QueryType
    reason: str


# ── Pattern lists ──────────────────────────────────────────────────────────────

_SIMPLE_PATTERNS = [
    r"tôi (muốn|thích|cần) ăn",
    r"cho tôi (ăn|thử|gợi ý)",
    r"ăn gì (ngon|bây giờ|hôm nay|cho tôi)",
    r"món gì ngon",
    r"gợi ý (món|đồ ăn|quán)",
    r"giá (bao nhiêu|thế nào|như thế nào)",
    r"so sánh giá",
    r"bao nhiêu tiền",
    r".{1,30} (ngon không|có ngon không)",
    r".{1,30} là (món|đồ ăn|thức ăn) gì",
    r".{1,30} (làm từ|gồm|có những)",
    # Kông dấu (no diacritics)
    r"toi (muon|thich|can) an",
    r"cho toi (an|thu|goi y)",
    r"an gi[\s]*(ngon|bay gio|hom nay|cho toi)",
    r"goi y (mon|do an|quan)",
    r"gia bao nhieu",
    r"bao nhieu tien",
    r"so sanh gia",
]

_COMPLEX_PATTERNS = [
    r"gần (tôi|đây|nhất|chỗ tôi|vị trí)",
    r"quán (gần|xung quanh|khu vực)",
    r"tìm (quán|chỗ ăn|nhà hàng)",
    r"trong vòng \d+ (km|phút đi)",
    r"bây giờ (nên|có thể|muốn)",
    r"(tối|trưa|sáng|chiều) (nay|hôm nay|này)",
    r"lúc (này|bây giờ|\d+h)",
    r"(đang|hiện tại) (muốn|cần|tìm)",
    r"vừa .+ vừa",
    r"chỉ (đường|tôi|cách đi)",
    r"làm sao (đến|tới|đi)",
]

_HEAVY_PATTERNS = [
    r"so sánh.+(với|và|vs).+(với|và|vs)",
    r"(kế hoạch|lịch).+(ăn|bữa).+(cả ngày|hôm nay)",
]

_COMPILED_SIMPLE  = [re.compile(p, re.IGNORECASE) for p in _SIMPLE_PATTERNS]
_COMPILED_COMPLEX = [re.compile(p, re.IGNORECASE) for p in _COMPLEX_PATTERNS]
_COMPILED_HEAVY   = [re.compile(p, re.IGNORECASE) for p in _HEAVY_PATTERNS]


# ── Public API ─────────────────────────────────────────────────────────────────

def route_query(query: str, has_location: bool = False) -> RouteDecision:
    """Phân tích query và trả về quyết định model."""
    q = query.strip()
    length = len(q)

    # 1. Heavy: rất dài hoặc đa tầng phức tạp
    if length > 200 or any(p.search(q) for p in _COMPILED_HEAVY):
        return RouteDecision(
            model="gemini-pro",
            max_output_tokens=1500,
            query_type="heavy",
            reason="Query phức tạp nhiều tầng hoặc quá dài",
        )

    # 2. Complex: location / thời gian / đa điều kiện
    location_trigger = has_location and re.search(r"gần|xung quanh|khu vực", q, re.IGNORECASE)
    if location_trigger or any(p.search(q) for p in _COMPILED_COMPLEX) or length > 100:
        return RouteDecision(
            model="gemini-flash",
            max_output_tokens=800,
            query_type="complex",
            reason="Query có location/thời gian/đa điều kiện",
        )

    # 3. Simple: template response, $0
    return RouteDecision(
        model="local",
        max_output_tokens=256,
        query_type="simple",
        reason="Simple query – dùng template",
    )


def get_meal_time(hour: int) -> str:
    if 6 <= hour < 10:  return "Bữa sáng"
    if 10 <= hour < 14: return "Bữa trưa"
    if 14 <= hour < 17: return "Xế chiều"
    if 17 <= hour < 21: return "Bữa tối"
    return "Ăn đêm"


def build_system_prompt(tier: ModelTier, city: str, hour: int, user_address: str | None = None) -> str:
    meal = get_meal_time(hour)
    loc = f"User ở: {user_address}." if user_address else "Không có địa chỉ cụ thể."

    if tier == "local":
        return f"Bạn là AI ẩm thực. Thành phố: {city}. Giờ: {hour}h ({meal})."

    if tier == "gemini-flash":
        return (
            f"Bạn là trợ lý ẩm thực AI cho {city}. "
            f"Hiện tại: {hour}h ({meal}). {loc} "
            "Trả lời ngắn gọn, chính xác, bằng tiếng Việt."
        )

    return (
        f"Bạn là chuyên gia ẩm thực AI cho {city}.\n"
        f"Thời gian: {hour}h ({meal}). {loc}\n"
        "Nhiệm vụ: Tư vấn món ăn, tìm quán gần user, gợi ý phù hợp thời điểm.\n"
        "Luôn trả lời tiếng Việt, thân thiện, cụ thể và hữu ích."
    )
