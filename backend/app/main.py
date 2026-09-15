"""FastAPI application assembly (§4)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, applications, auth, career, coach, documents, jobs, misc, onboarding
from .config import get_settings
from .observability import ObservabilityMiddleware, configure_logging
from .security.rate_limit import RateLimitMiddleware
from .workers.runner import bind_loop

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bind_loop(asyncio.get_running_loop())
    jobs.reconcile_stale_analysis_runs()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Serah — job-seeker workspace from Shortlisted.",
    lifespan=lifespan,
)

def _cors_origins() -> list[str]:
    origin = settings.frontend_origin.rstrip("/")
    origins = [origin]
    if settings.app_env != "production":
        for alt in ("http://localhost:5173", "http://127.0.0.1:5173"):
            if alt not in origins:
                origins.append(alt)
    return origins


app.add_middleware(ObservabilityMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(career.router)
app.include_router(coach.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(documents.router)
app.include_router(misc.router)
app.include_router(onboarding.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
