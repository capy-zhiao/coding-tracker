"""FastAPI entry point.

Once running, http://localhost:8000/docs serves interactive OpenAPI documentation —
generated automatically by FastAPI from the type hints.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import llm
from .config import settings
from .deps import get_current_user
from .routers import auth, mock, problems, review, stats, templates

logging.basicConfig(level=logging.INFO)


def check_auth_settings() -> None:
    """Refuse to start half-configured: a github-mode server with a weak or missing
    session key would hand out forgeable sessions."""
    if settings.auth_mode not in ("local", "github"):
        raise RuntimeError(f"AUTH_MODE must be 'local' or 'github', not {settings.auth_mode!r}")
    if settings.auth_mode == "github":
        if len(settings.session_secret) < 32:
            raise RuntimeError("SESSION_SECRET must be at least 32 characters in github mode")
        if not (settings.github_client_id and settings.github_client_secret):
            raise RuntimeError("github mode needs GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET")


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_auth_settings()
    yield


# The schema is not created here: migrate.py runs the Alembic migrations before the app
# starts (start.sh and the Docker entrypoint both call it).
app = FastAPI(
    lifespan=lifespan,
    title="LeetCode Tracker API",
    description="Spaced-repetition tracker for the NeetCode 250",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "auth_mode": settings.auth_mode,
        "llm_enabled": llm.is_enabled(),
        "llm_provider": llm.provider_name(),
        "daily_caps": {"review": settings.daily_review_cap, "new": settings.daily_new_cap},
    }


# Every route except /health needs a user; in local mode that is the one local user.
app.include_router(auth.router)
for r in (problems.router, review.router, stats.router, mock.router, templates.router):
    app.include_router(r, dependencies=[Depends(get_current_user)])
