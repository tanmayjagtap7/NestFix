import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_status_cache: Dict[str, Any] = {"checked_at": 0, "payload": None}


def _frontend_ready() -> bool:
    return (FRONTEND_DIST / "index.html").is_file()


def _frontend_file(full_path: str) -> Optional[Path]:
    root = FRONTEND_DIST.resolve()
    candidate = (root / full_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


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
def root() -> Any:
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
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


@app.get("/{full_path:path}")
def frontend(full_path: str) -> FileResponse:
    """Serve the built site. Client-side pages such as /admin fall back to index.html."""
    if not _frontend_ready():
        raise HTTPException(status_code=404, detail="Not found")
    found = _frontend_file(full_path)
    if found is not None:
        return FileResponse(found)
    return FileResponse(FRONTEND_DIST / "index.html")
