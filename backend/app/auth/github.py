"""GitHub OAuth (the web application flow). Only the public profile is requested: no
scope, no access to repositories or private email. The access token is used once to read
the profile and then dropped; it is never stored."""
from urllib.parse import urlencode

import httpx

from ..config import settings

AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"


class GitHubError(Exception):
    pass


def callback_url() -> str:
    # Built from configuration, never from the request's Host header, so a forged Host
    # can't redirect the OAuth code somewhere else.
    return f"{settings.public_base_url}/api/auth/callback/github"


def authorize_url(state: str) -> str:
    query = {"client_id": settings.github_client_id, "redirect_uri": callback_url(),
             "state": state, "allow_signup": "true"}
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def exchange_code(code: str) -> str:
    """Trade the one-time code from the callback for an access token."""
    r = httpx.post(TOKEN_URL, timeout=10, headers={"Accept": "application/json"}, data={
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "code": code,
        "redirect_uri": callback_url(),
    })
    token = r.json().get("access_token") if r.status_code == 200 else None
    if not token:
        raise GitHubError(f"token exchange failed ({r.status_code})")
    return token


def fetch_user(token: str) -> dict:
    """id, login, name and avatar_url of the signed-in GitHub account."""
    r = httpx.get(USER_URL, timeout=10, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "leetcode-tracker",
    })
    if r.status_code != 200:
        raise GitHubError(f"profile request failed ({r.status_code})")
    return r.json()
