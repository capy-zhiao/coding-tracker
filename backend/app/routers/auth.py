"""Who is signed in. Local mode always answers with the one local user."""
from fastapi import APIRouter, Depends

from ..config import settings
from ..deps import effective_caps, get_current_user, user_today
from ..models import User
from ..schemas import MeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    review_cap, new_cap = effective_caps(user)
    return MeOut(
        id=user.id, login=user.login, display_name=user.display_name,
        avatar_url=user.avatar_url, provider=user.provider, is_owner=user.is_owner,
        is_demo=user.is_demo, ai_enabled=user.ai_enabled, timezone=user.timezone,
        daily_review_cap=review_cap, daily_new_cap=new_cap,
        auth_mode=settings.auth_mode, today=user_today(user),
    )
