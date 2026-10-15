"""Signing in. Local mode always answers with the one local user; github mode signs in
with GitHub OAuth and keeps the session in a signed cookie (app/auth/session.py)."""
import logging
import secrets
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..auth import github
from ..auth.session import STATE_COOKIE, clear_session, secure_cookies, set_session
from ..config import settings
from ..database import get_db
from ..deps import effective_caps, get_current_user, user_today
from ..models import User
from ..schemas import MeOut

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    review_cap, new_cap = effective_caps(user)
    return MeOut(
        id=user.id, login=user.login, display_name=user.display_name,
        avatar_url=user.avatar_url, provider=user.provider, is_owner=user.is_owner,
        is_demo=user.is_demo, ai_enabled=user.is_owner and llm.is_enabled(),
        timezone=user.timezone,
        daily_review_cap=review_cap, daily_new_cap=new_cap,
        auth_mode=settings.auth_mode, today=user_today(user),
    )


def _require_github_mode() -> None:
    if settings.auth_mode != "github":
        raise HTTPException(404, "Sign-in is off: this server runs in local mode")


@router.get("/login/github")
def login_github():
    """Send the browser to GitHub. The random state comes back with the callback and must
    match the cookie set here, so a callback this browser didn't start is refused."""
    _require_github_mode()
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(github.authorize_url(state), status_code=302)
    response.set_cookie(STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax",
                        secure=secure_cookies(), path="/")
    return response


@router.get("/callback/github")
def callback_github(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    _require_github_mode()
    if error:                           # e.g. the user pressed Cancel on GitHub
        response = RedirectResponse("/", status_code=302)
        response.delete_cookie(STATE_COOKIE, path="/")
        return response
    expected = request.cookies.get(STATE_COOKIE)
    if not (code and state and expected and secrets.compare_digest(state, expected)):
        return _sign_in_failed("state missing or not matching")
    try:
        profile = github.fetch_user(github.exchange_code(code))
    except (github.GitHubError, httpx.HTTPError) as e:
        return _sign_in_failed(f"GitHub: {e}")

    user = _upsert_github_user(db, profile)
    response = RedirectResponse("/", status_code=302)
    set_session(response, user.id)
    response.delete_cookie(STATE_COOKIE, path="/")
    return response


def _sign_in_failed(reason: str) -> RedirectResponse:
    """The callback is a full-page visit, so a failure goes back to the sign-in page with
    a flag it turns into a message, rather than a bare JSON error."""
    log.warning("GitHub sign-in failed: %s", reason)
    response = RedirectResponse("/?signin=failed", status_code=302)
    response.delete_cookie(STATE_COOKIE, path="/")
    return response


def _upsert_github_user(db: Session, profile: dict) -> User:
    provider_id = str(profile["id"])     # the login can be renamed; the id can't
    user = db.scalar(select(User).where(User.provider == "github",
                                        User.provider_id == provider_id))
    if user is None:
        user = User(provider="github", provider_id=provider_id, login=profile["login"])
        db.add(user)
    user.login = profile["login"]
    user.display_name = profile.get("name") or profile["login"]
    user.avatar_url = profile.get("avatar_url") or ""
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    owner = settings.owner_github_login.strip().lower()
    user.is_owner = bool(owner) and user.login.lower() == owner
    user.ai_enabled = user.is_owner      # the server's own LLM key is the owner's
    db.commit()
    return user


@router.post("/logout", status_code=204)
def logout():
    response = Response(status_code=204)
    clear_session(response)
    return response
