"""
simple_handler.py – Template-based responses cho simple queries.
Không gọi Gemini API → chi phí $0, tốc độ tức thì.
"""
import re
from typing import Optional
from .models import FoodItem


# ── Intent Detection ──────────────────────────────────────────────────────────

def parse_intent(query: str) -> tuple[str, str, Optional[str]]:
    """
    Trả về (intent, keyword, second_keyword).
    intent: 'want_to_eat' | 'price_query' | 'price_compare' | 'suggest' | 'unknown'
    Hỗ trợ cả tiếng Việt có dấu và không dấu.
    """
    q = query.lower().strip()

    # So sánh giá hai món
    m = re.search(r"so s[aá]nh\s+(.+?)\s+(?:v[aà]|v[oớ]i|vs)\s+(.+?)(?:\s|$)", q, re.IGNORECASE)
    if m:
        return "price_compare", m.group(1).strip(), m.group(2).strip()

    # Hỏi giá
    m = re.search(r"(.+?)\s+(?:gi[aá] bao nhi[eê]u|bao nhi[eê]u ti[eề]n|gi[aá] th[eế] n[aà]o)", q, re.IGNORECASE)
    if m:
        return "price_query", m.group(1).strip(), None

    # Muốn ăn X – có dấu
    m = re.search(r"(?:t[oô]i (?:mu[oố]n|th[iíì]ch|c[aầ]n) [aă]n|cho t[oô]i [aă]n|[aă]n\s+)(.+?)(?:\s+ngon)?(?:\s*$|\.)", q, re.IGNORECASE)
    if m:
        return "want_to_eat", m.group(1).strip(), None

    # Muốn ăn X – không dấu
    m = re.search(r"(?:toi (?:muon|thich|can) an|cho toi an|toi an)\s+(.+?)(?:\s*$|\.)", q, re.IGNORECASE)
    if m:
        return "want_to_eat", m.group(1).strip(), None

    # Gợi ý – có và không dấu
    if re.search(r"g[oợ]i [yý]|suggest|recommend|goi y", q, re.IGNORECASE):
        m = re.search(r"(?:g[oợ]i [yý]|goi y|suggest)\s+(?:m[oó]n\s+)?(.+?)(?:\s|$)", q, re.IGNORECASE)
        return "suggest", (m.group(1).strip() if m else ""), None

    return "unknown", q[:40], None


# ── Price Formatting ──────────────────────────────────────────────────────────

def _fmt_price(mn: int, mx: int) -> str:
    if mn <= 1 and mx <= 1:
        return "Chưa có giá"
    if mn == mx:
        return f"{mx // 1000}k"
    return f"{mn // 1000}k–{mx // 1000}k"


# ── Response Templates ────────────────────────────────────────────────────────

def _resp_want_to_eat(keyword: str, items: list[FoodItem]) -> str:
    if not items:
        return f"Xin lỗi, chưa tìm thấy quán **{keyword}** nào. Thử từ khoá khác nhé! 🙏"
    top = items[:5]
    lines = [
        f"{i+1}. **{r.ten_quan}** ({r.ten_mon})\n"
        f"   📍 {r.dia_chi}, {r.quan}\n"
        f"   💰 {_fmt_price(r.gia_min, r.gia_max)} đ"
        for i, r in enumerate(top)
    ]
    return (
        f"Tìm được **{len(items)} quán {keyword}**! Top {len(top)} dưới đây 🍽️\n\n"
        + "\n\n".join(lines)
    )


def _resp_price(keyword: str, items: list[FoodItem]) -> str:
    if not items:
        return f"Chưa có thông tin giá của **{keyword}**."
    priced = [r for r in items if r.gia_min > 1 or r.gia_max > 1][:5]
    if not priced:
        return f"Tìm thấy {len(items)} quán **{keyword}** nhưng chưa có giá cụ thể."
    lines = [f"• **{r.ten_quan}**: {_fmt_price(r.gia_min, r.gia_max)} đ" for r in priced]
    low  = min(r.gia_min for r in priced if r.gia_min > 1)
    high = max(r.gia_max for r in priced if r.gia_max > 1)
    return (
        f"💰 **Giá {keyword}** tham khảo:\n\n"
        + "\n".join(lines)
        + f"\n\n*Dao động: {_fmt_price(low, high)} đ*"
    )


def _resp_compare(kw1: str, items1: list[FoodItem], kw2: str, items2: list[FoodItem]) -> str:
    def avg(lst):
        v = [r for r in lst if r.gia_min > 1 or r.gia_max > 1]
        if not v: return None
        return sum((r.gia_min + r.gia_max) / 2 for r in v) / len(v)

    a1, a2 = avg(items1), avg(items2)
    cmp = ""
    if a1 and a2:
        if a1 < a2:
            cmp = f"\n\n👉 **{kw1}** thường rẻ hơn {kw2}"
        elif a2 < a1:
            cmp = f"\n\n👉 **{kw2}** thường rẻ hơn {kw1}"
        else:
            cmp = "\n\n👉 Hai món có giá **tương đương**"

    def block(name, lst):
        if not lst: return f"**{name}**: Không có dữ liệu"
        return f"**{name}**: từ {_fmt_price(lst[0].gia_min, lst[0].gia_max)} đ (VD: {lst[0].ten_quan})"

    return f"💰 **So sánh giá:**\n\n{block(kw1, items1)}\n{block(kw2, items2)}{cmp}"


def _resp_suggest(keyword: str, items: list[FoodItem], meal_time: str) -> str:
    if not items:
        return "Không tìm được gợi ý phù hợp, thử từ khoá khác nhé!"
    top = items[:3]
    lines = [
        f"{i+1}. **{r.ten_mon}** tại {r.ten_quan} – {_fmt_price(r.gia_min, r.gia_max)} đ"
        for i, r in enumerate(top)
    ]
    label = f" {keyword}" if keyword else ""
    return f"🍽️ **Gợi ý{label} {meal_time}:**\n\n" + "\n".join(lines)


# ── Main Handler ──────────────────────────────────────────────────────────────

async def handle_simple(
    query: str,
    search_fn,           # async (keyword: str, limit: int) -> list[FoodItem]
    hour: int,
    meal_time: str,
) -> tuple[str, list[FoodItem], bool]:
    """
    Trả về (response_text, food_items, was_handled).
    was_handled=False nghĩa là cần fallback lên Gemini.
    """
    intent, kw, kw2 = parse_intent(query)

    if intent == "want_to_eat":
        items = await search_fn(kw, 10)
        return _resp_want_to_eat(kw, items), items, True

    if intent == "price_query":
        items = await search_fn(kw, 8)
        return _resp_price(kw, items), items, True

    if intent == "price_compare":
        import asyncio
        items1, items2 = await asyncio.gather(search_fn(kw, 5), search_fn(kw2 or "", 5))
        return _resp_compare(kw, items1, kw2 or "", items2), [*items1, *items2], True

    if intent == "suggest":
        items = await search_fn(kw or meal_time, 8)
        return _resp_suggest(kw, items, meal_time), items, True

    # unknown → fallback
    return "", [], False
