import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, SessionLocal, engine
from app.routers import employees, employers, housing
from app.seed import seed_if_empty
from app.services.geo import ensure_employer_columns, place_default_workplace
from app.services.bright_data_service import BrightDataService
from app.services.gemini_service import GeminiService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("nestfix")

_status_cache: Dict[str, Any] = {"checked_at": 0, "payload": None}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_employer_columns()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        place_default_workplace(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Nestfix", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_origin_regex=r"https://[A-Za-z0-9-]+\.ngrok-free\.(app|dev)|https://[A-Za-z0-9-]+\.ngrok\.(app|dev|io)",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(employers.router, prefix="/employers", tags=["employers"])
app.include_router(employees.router, prefix="/employees", tags=["employees"])
app.include_router(housing.router, prefix="/housing", tags=["housing"])


@app.get("/")
def root() -> Dict[str, str]:
    return {"name": "Nestfix", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> Dict[str, Any]:
    now = time.time()
    if _status_cache["payload"] is None or now - _status_cache["checked_at"] > 300:
        bright = BrightDataService().integration_snapshot()
        gemini = GeminiService().integration_snapshot()
        _status_cache["payload"] = {"bright_data": bright, "gemini": gemini}
        _status_cache["checked_at"] = now
    return {"status": "ok", "integrations": _status_cache["payload"]}
