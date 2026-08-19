import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.config import ENVIRONMENT, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
from app.db import get_db
from app.models import Business
from app.services.sms import send_sms
from app.templates_env import templates

router = APIRouter()

RESET_CODE_TTL_MINUTES = 15


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _find_business_by_email(db: Session, email: str) -> Business | None:
    return db.query(Business).filter(func.lower(Business.owner_email) == _normalize_email(email)).first()


@router.get("/login")
def login_form(request: Request, reset: str = ""):
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": None,
            "show_demo_hint": ENVIRONMENT != "production",
            "password_reset": reset == "1",
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    business = _find_business_by_email(db, email)
    if not business or not verify_password(password, business.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or password", "show_demo_hint": ENVIRONMENT != "production"},
            status_code=401,
        )
    request.session["business_id"] = business.id
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/forgot-password")
def forgot_password_form(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html", {})


@router.post("/forgot-password")
def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    normalized_email = _normalize_email(email)
    business = _find_business_by_email(db, normalized_email)
    dev_code = ""
    if business:
        code = f"{secrets.randbelow(1000000):06d}"
        business.password_reset_code = code
        business.password_reset_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            minutes=RESET_CODE_TTL_MINUTES
        )
        db.add(business)
        db.commit()
        send_sms(
            db,
            business,
            business.owner_phone,
            f"Your CallBridge password reset code is {code}. It expires in {RESET_CODE_TTL_MINUTES} minutes.",
        )
        # No live Twilio account connected — nothing was actually texted, so surface the
        # code directly instead of leaving the page looking like it silently did nothing.
        if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
            dev_code = code
    # Redirect regardless of whether the email matched — don't reveal which emails are registered.
    url = f"/reset-password?email={normalized_email}"
    if dev_code:
        url += f"&dev_code={dev_code}"
    return RedirectResponse(url=url, status_code=303)


@router.get("/reset-password")
def reset_password_form(request: Request, email: str = "", dev_code: str = ""):
    return templates.TemplateResponse(
        request, "reset_password.html", {"error": None, "email": email, "dev_code": dev_code}
    )


@router.post("/reset-password")
def reset_password_submit(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    business = _find_business_by_email(db, email)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    code_matches = business and business.password_reset_code and secrets.compare_digest(
        business.password_reset_code, code.strip()
    )
    not_expired = business and business.password_reset_expires_at and business.password_reset_expires_at > now
    if not (code_matches and not_expired):
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {"error": "That code is invalid or has expired.", "email": email},
            status_code=400,
        )

    business.password_hash = hash_password(password)
    business.password_reset_code = None
    business.password_reset_expires_at = None
    db.add(business)
    db.commit()
    return RedirectResponse(url="/login?reset=1", status_code=303)
