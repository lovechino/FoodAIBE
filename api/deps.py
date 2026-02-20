"""
deps.py – Dependency Injection: singleton service instances.
Khởi tạo 1 lần duy nhất khi server start.
"""
import os
from .core.router import QueryRouter
from .core.search import SearchService
from .core.gemini import GeminiService
from .core.simple import SimpleQueryHandler
from .core.prompt import PromptBuilder
from .handlers.chat_handler import ChatHandler
from .handlers.search_handler import SearchHandler
from .handlers.suggest_handler import SuggestHandler
from .handlers.nearby_handler import NearbyHandler

# ── Core singletons ────────────────────────────────────────────────────────────

_router  = QueryRouter()
_search  = SearchService(data_dir=os.getenv("DATA_DIR", "./data"))
_prompts = PromptBuilder()
_gemini  = GeminiService(
    api_key=os.getenv("GEMINI_API_KEY", ""),
    prompt_builder=_prompts,
)
_simple = SimpleQueryHandler()

# ── Handler singletons ─────────────────────────────────────────────────────────

_chat    = ChatHandler(_router, _search, _simple, _gemini)
_search_h = SearchHandler(_search)
_suggest  = SuggestHandler(_search, _gemini)
_nearby   = NearbyHandler(_search, _gemini)


# ── Getters (dùng trong routes) ────────────────────────────────────────────────

def get_router()         -> QueryRouter:      return _router
def get_search()         -> SearchService:    return _search
def get_gemini()         -> GeminiService:    return _gemini
def get_simple()         -> SimpleQueryHandler: return _simple
def get_chat_handler()   -> ChatHandler:      return _chat
def get_search_handler() -> SearchHandler:    return _search_h
def get_suggest_handler()-> SuggestHandler:   return _suggest
def get_nearby_handler() -> NearbyHandler:    return _nearby
