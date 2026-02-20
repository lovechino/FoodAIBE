"""
core/simple.py – SimpleQueryHandler class.
Trách nhiệm: xử lý simple queries bằng template (chi phí $0).
"""
import re
import asyncio
from typing import Optional, Callable, Awaitable
from ..models import FoodItem

SearchFn = Callable[[str, int], Awaitable[list[FoodItem]]]


class SimpleQueryHandler:
    """Template-based handler cho simple queries – không gọi Gemini."""

    # ── Public API ─────────────────────────────────────────────────────────────

    async def handle(
        self,
        query: str,
        search_fn: SearchFn,
        hour: int,
    ) -> tuple[str, list[FoodItem], bool]:
        """
        Xử lý query. Trả về (reply, items, was_handled).
        was_handled=False → caller cần fallback lên Gemini.
        """
        intent, kw, kw2 = self.parse_intent(query)
        if intent == "want_to_eat":
            return await self._handle_want(kw, search_fn)
        if intent == "price_query":
            return await self._handle_price(kw, search_fn)
        if intent == "price_compare":
            return await self._handle_compare(kw, kw2 or "", search_fn)
        if intent == "suggest":
            return await self._handle_suggest(kw, search_fn, hour)
        return "", [], False

    def parse_intent(self, query: str) -> tuple[str, str, Optional[str]]:
        """Trích xuất (intent, keyword, second_keyword) từ query."""
        q = query.lower().strip()
        return (
            self._try_compare(q)
            or self._try_price(q)
            or self._try_want(q)
            or self._try_suggest(q)
            or ("unknown", q[:40], None)
        )

    # ── Intent parsers ─────────────────────────────────────────────────────────

    def _try_compare(self, q: str) -> Optional[tuple]:
        m = re.search(r"so s[aá]nh\s+(.+?)\s+(?:v[aà]|v[oớ]i|vs)\s+(.+?)(?:\s|$)", q, re.I)
        return ("price_compare", m.group(1).strip(), m.group(2).strip()) if m else None

    def _try_price(self, q: str) -> Optional[tuple]:
        m = re.search(r"(.+?)\s+(?:gi[aá] bao nhi[eê]u|bao nhi[eê]u ti[eề]n|gi[aá] th[eế] n[aà]o)", q, re.I)
        return ("price_query", m.group(1).strip(), None) if m else None

    def _try_want(self, q: str) -> Optional[tuple]:
        m = re.search(
            r"(?:t[oô]i (?:mu[oố]n|th[iíì]ch|c[aầ]n) [aă]n"
            r"|cho t[oô]i [aă]n"
            r"|toi (?:muon|thich|can) an"
            r"|cho toi an)\s+(.+?)(?:\s*$|\.)",
            q, re.I,
        )
        return ("want_to_eat", m.group(1).strip(), None) if m else None

    def _try_suggest(self, q: str) -> Optional[tuple]:
        if not re.search(r"g[oợ]i [yý]|goi y|suggest|recommend", q, re.I):
            return None
        m = re.search(r"(?:g[oợ]i [yý]|goi y|suggest)\s+(?:m[oó]n\s+)?(.+?)(?:\s|$)", q, re.I)
        return ("suggest", m.group(1).strip() if m else "", None)

    # ── Response handlers ──────────────────────────────────────────────────────

    async def _handle_want(self, kw: str, fn: SearchFn) -> tuple:
        items = await fn(kw, 10)
        return self._resp_want(kw, items), items, True

    async def _handle_price(self, kw: str, fn: SearchFn) -> tuple:
        items = await fn(kw, 8)
        return self._resp_price(kw, items), items, True

    async def _handle_compare(self, kw1: str, kw2: str, fn: SearchFn) -> tuple:
        items1, items2 = await asyncio.gather(fn(kw1, 5), fn(kw2, 5))
        return self._resp_compare(kw1, items1, kw2, items2), [*items1, *items2], True

    async def _handle_suggest(self, kw: str, fn: SearchFn, hour: int) -> tuple:
        from .router import QueryRouter
        meal = QueryRouter.get_meal_time(hour)
        items = await fn(kw or meal, 8)
        return self._resp_suggest(kw, items, meal), items, True

    # ── Templates ──────────────────────────────────────────────────────────────

    def _resp_want(self, kw: str, items: list[FoodItem]) -> str:
        if not items:
            return f"Chưa tìm thấy quán **{kw}** nào. Thử từ khoá khác nhé! 🙏"
        lines = [
            f"{i+1}. **{r.ten_quan}** ({r.ten_mon})\n"
            f"   📍 {r.dia_chi}, {r.quan}\n"
            f"   💰 {self._fmt(r.gia_min, r.gia_max)}"
            for i, r in enumerate(items[:5])
        ]
        return f"Tìm được **{len(items)} quán {kw}** 🍽️\n\n" + "\n\n".join(lines)

    def _resp_price(self, kw: str, items: list[FoodItem]) -> str:
        priced = [r for r in items if r.gia_min > 1 or r.gia_max > 1][:5]
        if not priced:
            return f"Chưa có thông tin giá của **{kw}**."
        lines = [f"• **{r.ten_quan}**: {self._fmt(r.gia_min, r.gia_max)} đ" for r in priced]
        lo = min(r.gia_min for r in priced if r.gia_min > 1)
        hi = max(r.gia_max for r in priced if r.gia_max > 1)
        return f"💰 **Giá {kw}:**\n\n" + "\n".join(lines) + f"\n\n*Dao động: {self._fmt(lo, hi)} đ*"

    def _resp_compare(self, k1: str, i1: list, k2: str, i2: list) -> str:
        def avg(lst): return sum((r.gia_min+r.gia_max)/2 for r in lst if r.gia_min>1 or r.gia_max>1) / max(len(lst),1)
        cmp = ""
        if i1 and i2:
            a1, a2 = avg(i1), avg(i2)
            winner = k1 if a1 < a2 else k2
            cmp = f"\n\n👉 **{winner}** thường rẻ hơn"
        def blk(k, lst): return f"**{k}**: {self._fmt(lst[0].gia_min,lst[0].gia_max)} đ" if lst else f"**{k}**: N/A"
        return f"💰 So sánh giá:\n\n{blk(k1,i1)}\n{blk(k2,i2)}{cmp}"

    def _resp_suggest(self, kw: str, items: list[FoodItem], meal: str) -> str:
        if not items:
            return "Không tìm được gợi ý phù hợp."
        lines = [f"{i+1}. **{r.ten_mon}** – {r.ten_quan} – {self._fmt(r.gia_min,r.gia_max)} đ" for i,r in enumerate(items[:3])]
        label = f" {kw}" if kw else ""
        return f"🍽️ Gợi ý{label} {meal}:\n\n" + "\n".join(lines)

    @staticmethod
    def _fmt(mn: int, mx: int) -> str:
        if mn <= 1 and mx <= 1: return "Chưa có giá"
        if mn == mx: return f"{mx//1000}k"
        return f"{mn//1000}k–{mx//1000}k"
