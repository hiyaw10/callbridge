from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import CALENDLY_URL
from app.db import get_db
from app.models import Lead
from app.rate_limit import limiter
from app.templates_env import templates

router = APIRouter()


@router.get("/book-a-call")
def book_a_call_form(request: Request):
    return templates.TemplateResponse(request, "book_a_call.html", {"error": None})


@router.post("/book-a-call")
@limiter.limit("10/minute")
def book_a_call_submit(
    request: Request,
    contact_name: str = Form(...),
    business_name: str = Form(...),
    business_address: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
):
    lead = Lead(
        contact_name=contact_name.strip(),
        business_name=business_name.strip(),
        business_address=business_address.strip(),
        phone=phone.strip(),
    )
    db.add(lead)
    db.commit()

    # Hand off to the actual booking calendar, prefilled with what we already know
    # so they don't have to type their name again.
    redirect_url = f"{CALENDLY_URL}?{urlencode({'name': lead.contact_name})}"
    return RedirectResponse(url=redirect_url, status_code=303)
