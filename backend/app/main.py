import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.admin_routes import admin_router, announcement_router
from app.ai_routes import router as ai_router
from app.auth_routes import router as auth_router
from app.coach_routes import router as coach_router
from app.config import BACKEND_DIR, settings
from app.dashboard_routes import router as dashboard_router
from app.database import SessionLocal, engine, get_db
from app.errors import request_validation_error
from app.models import SystemSchema
from app.nutrition_routes import router as nutrition_router
from app.profile import router as profile_router
from app.planning_routes import plan_router, report_router
from app.reference_routes import exercise_router, food_router
from app.workout_routes import router as workout_router
from app.services.ai.worker import run_worker

FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(application: FastAPI):
    worker = (
        asyncio.create_task(run_worker(SessionLocal, settings), name="kinetix-ai-worker")
        if settings.run_ai_worker
        else None
    )
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        engine.dispose()


app = FastAPI(
    title="KINETIX AI",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_exception_handler(RequestValidationError, request_validation_error)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(exercise_router)
app.include_router(food_router)
app.include_router(dashboard_router)
app.include_router(ai_router)
app.include_router(workout_router)
app.include_router(nutrition_router)
app.include_router(report_router)
app.include_router(plan_router)
app.include_router(coach_router)
app.include_router(admin_router)
app.include_router(announcement_router)


@app.get("/api/v1/health/live", tags=["health"])
def health_live():
    return {"status": "ok"}

@app.get("/api/v1/health", tags=["health"])
def health(db: Annotated[Session, Depends(get_db)]):
    try:
        component = db.scalar(select(SystemSchema.component).where(SystemSchema.id == 1))
        if component != "kinetix-ai":
            raise HTTPException(status_code=503, detail="Database migrations are required")
    except SQLAlchemyError:
        # Never leak database URLs, credentials, or driver diagnostics to clients.
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable", "environment": settings.app_env},
        )
    return {"status": "ok", "database": "ok", "environment": settings.app_env}


@app.get("/{requested_path:path}", include_in_schema=False)
def frontend(requested_path: str):
    if requested_path == "api" or requested_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    # Resolve before serving so traversal and symlinks cannot escape the build.
    root = FRONTEND_DIST.resolve()
    candidate = (root / requested_path).resolve()
    if not candidate.is_relative_to(root) or any(part.startswith(".") for part in Path(requested_path).parts):
        raise HTTPException(status_code=404, detail="Not found")
    if candidate.is_file():
        return FileResponse(candidate)
    # Missing assets must never receive HTML with a successful response.
    if requested_path == "assets" or requested_path.startswith("assets/") or Path(requested_path).suffix:
        raise HTTPException(status_code=404, detail="Asset not found")
    index = root / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Client build not installed; use the Vite development server")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
