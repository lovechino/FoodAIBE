"""
handlers/suggest_handler.py – SuggestHandler class.
Trách nhiệm: điều phối gợi ý theo bữa ăn hiện tại.
"""
import logging
from ..core.router import QueryRouter
from ..core.search import SearchService
from ..core.gemini import GeminiService
from ..models import SuggestResponse

logger = logging.getLogger(__name__)

MEAL_KEYWORDS: dict[str, str] = {
    "Bữa sáng": "bún phở bánh mì xôi",
    "Bữa trưa": "cơm bún mì",
    "Xế chiều": "ăn vặt chè bánh",
    "Bữa tối":  "lẩu nướng cơm",
    "Ăn đêm":   "cháo mì bún",
}
_FALLBACK_MSG = "Bạn có thể thử các món phổ biến trong vùng."


class SuggestHandler:
    """Xử lý /suggest endpoint."""

    def __init__(self, search: SearchService, gemini: GeminiService) -> None:
        self._search = search
        self._gemini = gemini

    async def handle(self, city: str, hour: int) -> SuggestResponse:
        meal_time = QueryRouter.get_meal_time(hour)
        items     = await self._search.hybrid_search(city, MEAL_KEYWORDS.get(meal_time, ""), top_k=8)
        reply     = await self._build_reply(city, hour, meal_time, items)
        return SuggestResponse(meal_time=meal_time, suggestions=items, reply=reply, model_used="gemini-flash")

    async def _build_reply(self, city, hour, meal_time, items) -> str:
        if not items:
            return f"Hiện tại {meal_time}, {_FALLBACK_MSG}"
        food_names = ", ".join({r.ten_mon for r in items[:5]})
        prompt = (
            f"Bây giờ {hour}h ({meal_time}). Danh sách: {food_names}. "
            "Gợi ý 2-3 món phù hợp nhất, kèm lý do ngắn."
        )
        return await self._gemini.chat(prompt, city, "gemini-flash", 400, food_context=items)
