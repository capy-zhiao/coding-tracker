"""FastAPI entry point.

Once running, http://localhost:8000/docs serves interactive OpenAPI documentation —
generated automatically by FastAPI from the type hints.
"""
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import llm
from .config import settings
from .deps import get_current_user
from .routers import auth, mock, problems, review, stats, templates

logging.basicConfig(level=logging.INFO)


# The schema is not created here: migrate.py runs the Alembic migrations before the app
# starts (start.sh and the Docker entrypoint both call it).
app = FastAPI(
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
