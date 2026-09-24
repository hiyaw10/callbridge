import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_password, require_admin
from app.config import ADMIN_TOKEN, GA_MEASUREMENT_ID
from app.db import get_db
from app.models import Broadcast, Business, Call, Job, Lead, TextMessage
from app.templates_env import templates

router = APIRouter()

MONTHLY_PRICE = 99
PAGE_SIZE = 15


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
    return RedirectResponse(url="/admin/analytics", status_code=303)


@router.get("/admin/logout")
def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    return RedirectResponse(url="/admin/login", status_code=303)


# Date-range filter options for the platform activity section, matching the business
# dashboard's own Calls filter for a familiar pattern.
_ACTIVITY_RANGES = {"7": 7, "30": 30, "90": 90, "all": None}


@router.get("/admin/analytics", dependencies=[Depends(require_admin)])
def analytics(request: Request, days: str = "30", db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    days_n = _ACTIVITY_RANGES.get(days, 30)
    cutoff = now - timedelta(days=days_n) if days_n else None

    business_count = db.query(Business).count()
    lead_count = db.query(Lead).count()
    leads_last_30 = db.query(Lead).filter(Lead.created_at >= now - timedelta(days=30)).count()

    # Best-effort lead -> signup match: a lead whose email was later used as a business's
    # login. Not a tracked funnel (leads and businesses aren't linked by ID — a business is
    # created manually by an admin after the onboarding call) so this only catches the case
    # where the same email was used both times; it undercounts real conversions where it wasn't.
    owner_emails = {b.owner_email for b in db.query(Business.owner_email).all()}
    matched_leads = db.query(Lead).filter(Lead.email.in_(owner_emails)).count() if owner_emails else 0

    call_query = db.query(Call)
    text_query = db.query(TextMessage).filter(TextMessage.direction == "outbound")
    job_query = db.query(Job)
    broadcast_query = db.query(Broadcast)
    if cutoff:
        call_query = call_query.filter(Call.timestamp >= cutoff)
        text_query = text_query.filter(TextMessage.timestamp >= cutoff)
        job_query = job_query.filter(Job.created_at >= cutoff)
        broadcast_query = broadcast_query.filter(Broadcast.created_at >= cutoff)

    calls = call_query.all()
    calls_total = len(calls)
    calls_missed = sum(1 for c in calls if c.status == "missed")
    calls_answered = calls_total - calls_missed

    texts_sent = text_query.count()
    jobs_completed = job_query.filter(Job.completed_at.isnot(None)).count()
    broadcasts = broadcast_query.all()
    broadcasts_sent = len(broadcasts)
    announcement_recipients = sum(b.recipient_count for b in broadcasts)

    # Sign-ups and leads by week, most recent 8 weeks (newest first), for a simple
    # growth-over-time view without pulling in a charting library.
    weeks = []
    for i in range(0, 8):
        week_start = (now - timedelta(days=now.weekday() + i * 7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=7)
        weeks.append(
            {
                "label": week_start.strftime("%b %-d"),
                "new_businesses": db.query(Business)
                .filter(Business.created_at >= week_start, Business.created_at < week_end)
                .count(),
                "new_leads": db.query(Lead)
                .filter(Lead.created_at >= week_start, Lead.created_at < week_end)
                .count(),
            }
        )

    return templates.TemplateResponse(
        request,
        "admin_analytics.html",
        {
            "business_count": business_count,
            "mrr": business_count * MONTHLY_PRICE,
            "lead_count": lead_count,
            "leads_last_30": leads_last_30,
            "matched_leads": matched_leads,
            "days": days,
            "calls_total": calls_total,
            "calls_missed": calls_missed,
            "calls_answered": calls_answered,
            "texts_sent": texts_sent,
            "jobs_completed": jobs_completed,
            "broadcasts_sent": broadcasts_sent,
            "announcement_recipients": announcement_recipients,
            "weeks": weeks,
            "ga_configured": bool(GA_MEASUREMENT_ID),
        },
    )


def _paginate(query, page: int):
    total = query.count()
    total_pages = max(1, -(-total // PAGE_SIZE))  # ceil division
    page = max(1, min(page, total_pages))
    items = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    return items, page, total_pages, total


def _search_leads(db: Session, q: str, show: str):
    query = db.query(Lead)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Lead.contact_name.ilike(like),
                Lead.business_name.ilike(like),
                Lead.business_address.ilike(like),
                Lead.email.ilike(like),
                Lead.phone.ilike(like),
            )
        )
    query = query.filter(Lead.archived_at.isnot(None)) if show == "archived" else query.filter(Lead.archived_at.is_(None))
    return query.order_by(Lead.created_at.desc())


def _search_businesses(db: Session, q: str, show: str):
    query = db.query(Business)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Business.name.ilike(like),
                Business.owner_email.ilike(like),
                Business.owner_phone.ilike(like),
                Business.twilio_number.ilike(like),
            )
        )
    query = (
        query.filter(Business.archived_at.isnot(None))
        if show == "archived"
        else query.filter(Business.archived_at.is_(None))
    )
    return query.order_by(Business.created_at.desc())


@router.get("/admin/leads", dependencies=[Depends(require_admin)])
def list_leads(request: Request, q: str = "", show: str = "active", page: int = 1, db: Session = Depends(get_db)):
    leads, page, total_pages, total = _paginate(_search_leads(db, q.strip(), show), page)
    return templates.TemplateResponse(
        request,
        "admin_leads.html",
        {"leads": leads, "q": q, "show": show, "page": page, "total_pages": total_pages, "total": total, "page_size": PAGE_SIZE},
    )


@router.post("/admin/leads/{lead_id}/notes", dependencies=[Depends(require_admin)])
def update_lead_notes(
    lead_id: int,
    request: Request,
    notes: str = Form(""),
    q: str = Form(""),
    show: str = Form("active"),
    page: int = Form(1),
    db: Session = Depends(get_db),
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    lead.notes = notes.strip() or None
    db.add(lead)
    db.commit()
    return RedirectResponse(url=f"/admin/leads?q={q}&show={show}&page={page}", status_code=303)


@router.post("/admin/leads/{lead_id}/archive", dependencies=[Depends(require_admin)])
def archive_lead(
    lead_id: int, q: str = Form(""), page: int = Form(1), db: Session = Depends(get_db)
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    lead.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(lead)
    db.commit()
    return RedirectResponse(url=f"/admin/leads?q={q}&page={page}", status_code=303)


@router.post("/admin/leads/{lead_id}/unarchive", dependencies=[Depends(require_admin)])
def unarchive_lead(
    lead_id: int, q: str = Form(""), page: int = Form(1), db: Session = Depends(get_db)
):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    lead.archived_at = None
    db.add(lead)
    db.commit()
    return RedirectResponse(url=f"/admin/leads?q={q}&show=archived&page={page}", status_code=303)


@router.get("/admin/businesses", dependencies=[Depends(require_admin)])
def list_businesses(
    request: Request, q: str = "", show: str = "active", page: int = 1, db: Session = Depends(get_db)
):
    businesses, page, total_pages, total = _paginate(_search_businesses(db, q.strip(), show), page)
    return templates.TemplateResponse(
        request,
        "admin_businesses.html",
        {
            "businesses": businesses,
            "error": None,
            "q": q,
            "show": show,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "page_size": PAGE_SIZE,
        },
    )


@router.post("/admin/businesses/{business_id}/archive", dependencies=[Depends(require_admin)])
def archive_business(
    business_id: int, q: str = Form(""), page: int = Form(1), db: Session = Depends(get_db)
):
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404)
    business.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(business)
    db.commit()
    return RedirectResponse(url=f"/admin/businesses?q={q}&page={page}", status_code=303)


@router.post("/admin/businesses/{business_id}/unarchive", dependencies=[Depends(require_admin)])
def unarchive_business(
    business_id: int, q: str = Form(""), page: int = Form(1), db: Session = Depends(get_db)
):
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404)
    business.archived_at = None
    db.add(business)
    db.commit()
    return RedirectResponse(url=f"/admin/businesses?q={q}&show=archived&page={page}", status_code=303)


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
        businesses, page, total_pages, total = _paginate(_search_businesses(db, "", "active"), 1)
        return templates.TemplateResponse(
            request,
            "admin_businesses.html",
            {
                "businesses": businesses,
                "error": "A business with that owner email or Twilio number already exists.",
                "q": "",
                "show": "active",
                "page": page,
                "total_pages": total_pages,
                "total": total,
                "page_size": PAGE_SIZE,
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
    password: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404)

    business.name = name.strip()
    business.owner_email = owner_email.strip().lower()
    business.owner_phone = owner_phone.strip()
    business.twilio_number = twilio_number.strip()
    business.notes = notes.strip() or None
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
