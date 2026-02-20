"""
handlers/nearby_handler.py – NearbyHandler class.
Trách nhiệm: tìm quán gần user bằng FAISS + Gemini ranking.
"""
import logging
from ..core.search import SearchService
from ..core.gemini import GeminiService
from ..models import NearbyRequest, NearbyResponse

logger = logging.getLogger(__name__)


class NearbyHandler:
    """Xử lý /nearby endpoint."""

    def __init__(self, search: SearchService, gemini: GeminiService) -> None:
        self._search = search
        self._gemini = gemini

    async def handle(self, req: NearbyRequest) -> NearbyResponse:
        """Bước 1: FAISS lấy candidates. Bước 2: Gemini xếp hạng."""
        candidates = await self._search.hybrid_search(req.city, req.query, top_k=15)
        reply      = await self._gemini.rank_nearby(candidates, req.user_address, req.city, req.query)
        return NearbyResponse(reply=reply, results=candidates[:10], model_used="gemini-flash")
