"""The session is a signed cookie holding the user's id. Nothing is stored server side.

Signed, not encrypted: the id is not a secret, but nobody can change it without the key,
and itsdangerous rejects anything tampered with or older than the max age. The cookie is
HttpOnly (scripts can't read it), SameSite=Lax (not sent on cross-site POSTs) and Secure
whenever the site is served over https.
"""
from fastapi import Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from ..config import settings

SESSION_COOKIE = "lt_session"
STATE_COOKIE = "lt_oauth_state"      # the OAuth state, for the few minutes of a sign-in


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="lt-session")


def _max_age() -> int:
    return settings.session_max_age_days * 86400


def secure_cookies() -> bool:
    return settings.public_base_url.startswith("https://")


def set_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE, _serializer().dumps({"uid": user_id}), max_age=_max_age(),
        httponly=True, samesite="lax", secure=secure_cookies(), path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax",
                           secure=secure_cookies())


def read_session(request: Request) -> int | None:
    """The signed-in user's id, or None if there's no valid, unexpired session."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        data = _serializer().loads(raw, max_age=_max_age())
    except BadSignature:              # also covers SignatureExpired
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return uid if isinstance(uid, int) else None
