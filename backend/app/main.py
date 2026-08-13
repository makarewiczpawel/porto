from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.errors import register_error_handlers
from app.routers import auth, content, quizzes, study

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="API aplikacji Porto — nauka portugalskiego europejskiego.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(auth.router)
app.include_router(content.router)
app.include_router(study.router)
app.include_router(quizzes.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "version": settings.version}
