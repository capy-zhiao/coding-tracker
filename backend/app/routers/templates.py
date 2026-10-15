"""Template blind-write drills.

The markdown notes had a practice ground where you wrote a template from memory, then
scrolled to the bottom and compared by eye. This automates the comparison half: the
reference stays hidden until you submit, and the grading is done by checkpoints rather
than by eye, so "I basically had it" stops being a judgement call.

Grading itself lives in blindwrite.py as pure functions; this module only wires it to HTTP.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..blindwrite import grade, suggested_grade
from ..database import get_db
from ..deps import get_current_user, states_for
from ..models import Problem, User
from ..schemas import BlindWriteIn, BlindWriteOut, StateOut, TemplateOut
from ..templates_ref import BY_NUMBER

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """All 15 drills with your SRS state, ordered by the roadmap chapter they belong to."""
    rows = db.scalars(
        select(Problem).where(Problem.kind == "template").order_by(Problem.number)
    )
    states = states_for(db, user.id, "template")
    out = []
    for p in rows:
        ref = BY_NUMBER.get(p.number)
        out.append(TemplateOut(
            number=p.number, title=p.title, chapter=p.chapter,
            check_count=len(ref.checks) if ref else 0,
            state=StateOut.model_validate(states[p.id]) if p.id in states else None,
        ))
    return out


@router.post("/{number}/check", response_model=BlindWriteOut)
def check_blindwrite(number: int, payload: BlindWriteIn):
    """Grade a blind-written template. Read-only — recording the attempt is a separate call,
    so you can check, read the diff, and retry without polluting the history."""
    result = grade(number, payload.code)
    if result is None:
        raise HTTPException(404, f"{number} is not a known template")
    return BlindWriteOut(
        number=result.number, name=result.name, passed=result.passed,
        similarity=result.similarity, checks=result.checks, missing=result.missing,
        diff=result.diff, verdict=result.verdict,
        suggested_grade=suggested_grade(result),
        reference=result.reference,
    )


@router.get("/{number}/reference")
def reveal_reference(number: int):
    """The reference implementation. Separate endpoint so the drill page can keep it out of
    the initial payload — having it in the browser would defeat the point."""
    ref = BY_NUMBER.get(number)
    if ref is None:
        raise HTTPException(404, f"{number} is not a known template")
    return {
        "number": ref.number,
        "name": ref.name,
        "reference": ref.reference,
        "checks": [{"id": c.id, "label": c.label, "why": c.why} for c in ref.checks],
    }
