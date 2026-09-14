import hmac

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_password, require_admin
from app.config import ADMIN_TOKEN
from app.db import get_db
from app.models import Business
from app.templates_env import templates

router = APIRouter()


@router.get("/admin/login")
def admin_login_form(request: Request):
    return templates.TemplateResponse(request, "admin_login.html", {"error": None})


@router.post("/admin/login")
def admin_login_submit(request: Request, token: str = Form(...)):
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        return templates.TemplateResponse(
            request, "admin_login.html", {"error": "Invalid admin token"}, status_code=401
        )
    request.session["is_admin"] = True
    return RedirectResponse(url="/admin/businesses", status_code=303)


@router.get("/admin/logout")
def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    return RedirectResponse(url="/admin/login", status_code=303)


@router.get("/admin/businesses", dependencies=[Depends(require_admin)])
def list_businesses(request: Request, db: Session = Depends(get_db)):
    businesses = db.query(Business).order_by(Business.created_at.desc()).all()
    return templates.TemplateResponse(
        request, "admin_businesses.html", {"businesses": businesses, "error": None}
    )


@router.post("/admin/businesses", dependencies=[Depends(require_admin)])
def create_business(
    request: Request,
    name: str = Form(...),
    owner_email: str = Form(...),
    owner_phone: str = Form(...),
    password: str = Form(...),
    twilio_number: str = Form(...),
    db: Session = Depends(get_db),
):
    business = Business(
        name=name.strip(),
        owner_email=owner_email.strip().lower(),
        owner_phone=owner_phone.strip(),
        password_hash=hash_password(password),
        twilio_number=twilio_number.strip(),
    )
    db.add(business)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        businesses = db.query(Business).order_by(Business.created_at.desc()).all()
        return templates.TemplateResponse(
            request,
            "admin_businesses.html",
            {
                "businesses": businesses,
                "error": "A business with that owner email or Twilio number already exists.",
            },
            status_code=400,
        )
    return RedirectResponse(url="/admin/businesses", status_code=303)


@router.get("/admin/businesses/{business_id}/edit", dependencies=[Depends(require_admin)])
def edit_business_form(business_id: int, request: Request, db: Session = Depends(get_db)):
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request, "admin_edit_business.html", {"business": business, "error": None}
    )


@router.post("/admin/businesses/{business_id}/edit", dependencies=[Depends(require_admin)])
def edit_business_submit(
    business_id: int,
    request: Request,
    name: str = Form(...),
    owner_email: str = Form(...),
    owner_phone: str = Form(...),
    twilio_number: str = Form(...),
    plan_tier: str = Form(...),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404)

    business.name = name.strip()
    business.owner_email = owner_email.strip().lower()
    business.owner_phone = owner_phone.strip()
    business.twilio_number = twilio_number.strip()
    business.plan_tier = plan_tier
    if password.strip():
        business.password_hash = hash_password(password.strip())

    db.add(business)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request,
            "admin_edit_business.html",
            {
                "business": business,
                "error": "That owner email or Twilio number is already used by another business.",
            },
            status_code=400,
        )
    return RedirectResponse(url="/admin/businesses", status_code=303)
