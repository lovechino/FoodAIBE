"""
main.py – FastAPI app entry point (slim wire-up only).
Chỉ kết nối routes và lifespan. Không chứa business logic.
"""
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import chat, search, ai, system, city
from .deps import get_search

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Preloading FAISS indexes…")
    get_search().preload_all()
    logger.info("✅ Ready.")
    yield
    logger.info("Shutdown.")


app = FastAPI(
    title="FoodTour AI API",
    description="AI-powered food assistant cho 6 thành phố Việt Nam.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(system.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(ai.router)
app.include_router(city.router)
