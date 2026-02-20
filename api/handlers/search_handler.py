"""
handlers/search_handler.py – SearchHandler class.
Trách nhiệm: điều phối search request.
"""
from ..core.search import SearchService
from ..models import SearchResponse


class SearchHandler:
    """Xử lý /search endpoint."""

    def __init__(self, search: SearchService) -> None:
        self._search = search

    async def handle(self, q: str, city: str, limit: int, mode: str) -> SearchResponse:
        if mode == "text":
            items = await self._search.text_search(city, q, limit)
        else:
            items = await self._search.hybrid_search(city, q, limit)
        return SearchResponse(items=items, total=len(items), city=city)
