from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator

from app.config import TWILIO_AUTH_TOKEN
from app.db import get_db
from app.models import Business
from app.services.missed_call import handle_call_status

router = APIRouter()


@router.post("/webhooks/twilio/call-status")
async def twilio_call_status(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    params = dict(form)

    if TWILIO_AUTH_TOKEN:
        signature = request.headers.get("X-Twilio-Signature", "")
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        if not validator.validate(str(request.url), params, signature):
            return PlainTextResponse("invalid signature", status_code=403)

    call_sid = params.get("CallSid")
    call_status = params.get("CallStatus")
    to_number = params.get("To")
    from_number = params.get("From")

    if not (call_sid and call_status and to_number and from_number):
        return PlainTextResponse("missing required fields", status_code=400)

    business = db.query(Business).filter(Business.twilio_number == to_number).first()
    if business:
        handle_call_status(db, business, call_sid, from_number, call_status)

    return PlainTextResponse("ok")
