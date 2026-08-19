from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import get_current_business
from app.db import get_db
from app.models import Business, Call, Job, TextMessage
from app.services.sms import send_sms
from app.services.templates import DEFAULT_MISSED_CALL_MESSAGE, DEFAULT_REVIEW_REQUEST_MESSAGE
from app.templates_env import templates

router = APIRouter()

DAYS_OPTIONS = {"7": 7, "30": 30, "90": 90}


@router.get("/dashboard")
def dashboard(
    request: Request,
    phone: str = "",
    status: str = "",
    days: str = "30",
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    phone = phone.strip()
    status = status if status in ("missed", "answered") else ""
    days_n = DAYS_OPTIONS.get(days)
    cutoff = _now() - timedelta(days=days_n) if days_n else None

    calls_query = db.query(Call).filter(Call.business_id == business.id)
    if phone:
        calls_query = calls_query.filter(Call.caller_number.ilike(f"%{phone}%"))
    if status:
        calls_query = calls_query.filter(Call.status == status)
    if cutoff:
        calls_query = calls_query.filter(Call.timestamp >= cutoff)
    calls = calls_query.order_by(Call.timestamp.desc()).limit(100).all()

    texts = (
        db.query(TextMessage)
        .filter(TextMessage.business_id == business.id, TextMessage.call_id.isnot(None))
        .all()
    )
    texts_by_call = {}
    for t in texts:
        texts_by_call.setdefault(t.call_id, []).append(t)

    jobs_query = db.query(Job).filter(Job.business_id == business.id)
    if phone:
        jobs_query = jobs_query.filter(Job.customer_phone.ilike(f"%{phone}%"))
    if cutoff:
        jobs_query = jobs_query.filter(Job.created_at >= cutoff)
    jobs = jobs_query.order_by(Job.created_at.desc()).limit(50).all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "current_business": business,
            "business": business,
            "calls": calls,
            "texts_by_call": texts_by_call,
            "jobs": jobs,
            "stats": _weekly_stats(db, business),
            "filter_phone": phone,
            "filter_status": status,
            "filter_days": days,
        },
    )


@router.post("/dashboard/calls/{call_id}/reply")
def reply_to_call(
    call_id: int,
    body: str = Form(...),
    phone: str = Form(""),
    status: str = Form(""),
    days: str = Form("30"),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    call = db.query(Call).filter(Call.id == call_id, Call.business_id == business.id).first()
    if not call:
        raise HTTPException(status_code=404)
    body = body.strip()
    if body:
        send_sms(db, business, call.caller_number, body, call_id=call.id)
    return RedirectResponse(url=_dashboard_url(phone, status, days), status_code=303)


@router.post("/dashboard/jobs")
def add_job(
    customer_phone: str = Form(...),
    phone: str = Form(""),
    status: str = Form(""),
    days: str = Form("30"),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    db.add(Job(business_id=business.id, customer_phone=customer_phone))
    db.commit()
    return RedirectResponse(url=_dashboard_url(phone, status, days), status_code=303)


@router.post("/dashboard/jobs/{job_id}/complete")
def complete_job(
    job_id: int,
    phone: str = Form(""),
    status: str = Form(""),
    days: str = Form("30"),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.business_id == business.id).first()
    if not job:
        raise HTTPException(status_code=404)
    if not job.completed_at:
        job.completed_at = _now()
        db.add(job)
        db.commit()
    return RedirectResponse(url=_dashboard_url(phone, status, days), status_code=303)


@router.get("/dashboard/settings")
def settings_form(
    request: Request,
    business: Business = Depends(get_current_business),
):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "current_business": business,
            "business": business,
            "missed_call_message": business.missed_call_message or DEFAULT_MISSED_CALL_MESSAGE,
            "review_request_message": business.review_request_message or DEFAULT_REVIEW_REQUEST_MESSAGE,
            "saved": False,
        },
    )


@router.post("/dashboard/settings")
def settings_save(
    request: Request,
    missed_call_message: str = Form(""),
    review_request_message: str = Form(""),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    missed_call_message = missed_call_message.strip()
    review_request_message = review_request_message.strip()
    business.missed_call_message = missed_call_message or None
    business.review_request_message = review_request_message or None
    db.add(business)
    db.commit()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "current_business": business,
            "business": business,
            "missed_call_message": business.missed_call_message or DEFAULT_MISSED_CALL_MESSAGE,
            "review_request_message": business.review_request_message or DEFAULT_REVIEW_REQUEST_MESSAGE,
            "saved": True,
        },
    )


def _dashboard_url(phone: str, status: str, days: str) -> str:
    params = {k: v for k, v in {"phone": phone, "status": status, "days": days}.items() if v}
    return "/dashboard" + (f"?{urlencode(params)}" if params else "")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _weekly_stats(db: Session, business: Business) -> dict:
    week_ago = _now() - timedelta(days=7)

    calls_this_week = db.query(Call).filter(Call.business_id == business.id, Call.timestamp >= week_ago)
    missed = calls_this_week.filter(Call.status == "missed").count()
    answered = calls_this_week.filter(Call.status == "answered").count()

    texts_sent = (
        db.query(TextMessage)
        .filter(
            TextMessage.business_id == business.id,
            TextMessage.call_id.isnot(None),
            TextMessage.status == "sent",
            TextMessage.timestamp >= week_ago,
        )
        .count()
    )

    # Distinct missed calls with at least one reply (auto or manual) — caps at 100%,
    # unlike a raw text count, which can exceed the number of missed calls.
    responded_missed_calls = (
        db.query(TextMessage.call_id)
        .join(Call, Call.id == TextMessage.call_id)
        .filter(
            TextMessage.business_id == business.id,
            TextMessage.status == "sent",
            Call.status == "missed",
            Call.timestamp >= week_ago,
        )
        .distinct()
        .count()
    )

    jobs_done = db.query(Job).filter(Job.business_id == business.id, Job.completed_at >= week_ago).count()

    return {
        "missed": missed,
        "answered": answered,
        "texts_sent": texts_sent,
        "jobs_done": jobs_done,
        "response_rate": round((responded_missed_calls / missed) * 100) if missed else None,
    }
