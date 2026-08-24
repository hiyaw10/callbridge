from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from app.config import TWILIO_AUTH_TOKEN
from app.db import get_db
from app.models import Business
from app.services.missed_call import handle_call_status

router = APIRouter()

# How long to ring the owner's phone before treating the call as missed. Kept short
# because carrier voicemail can pick up the call before Twilio's own timeout does —
# if voicemail wins the race, Twilio reports the call as answered either way.
DIAL_TIMEOUT_SECONDS = 15


def _validate_twilio_request(request: Request, params: dict) -> bool:
    if not TWILIO_AUTH_TOKEN:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    return validator.validate(str(request.url), params, signature)


@router.post("/webhooks/twilio/voice")
async def twilio_voice(request: Request, db: Session = Depends(get_db)):
    """"A call comes in" handler: dials the business owner's phone, and tells Twilio
    to report the outcome (answered vs no-answer/busy/canceled) to /call-status —
    that outcome, not the inbound call's own status, is what actually reflects
    whether a human picked up."""
    form = await request.form()
    params = dict(form)

    if not _validate_twilio_request(request, params):
        return PlainTextResponse("invalid signature", status_code=403)

    to_number = params.get("To")
    business = db.query(Business).filter(Business.twilio_number == to_number).first()

    response = VoiceResponse()
    if business and business.owner_phone:
        action_url = str(request.base_url).rstrip("/") + "/webhooks/twilio/call-status"
        response.dial(
            business.owner_phone,
            timeout=DIAL_TIMEOUT_SECONDS,
            action=action_url,
            method="POST",
        )
    return Response(content=str(response), media_type="application/xml")


@router.post("/webhooks/twilio/call-status")
async def twilio_call_status(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    params = dict(form)

    if not _validate_twilio_request(request, params):
        return PlainTextResponse("invalid signature", status_code=403)

    call_sid = params.get("CallSid")
    # DialCallStatus reflects whether the owner's phone actually answered — present when
    # this request is the <Dial action> callback. Fall back to CallStatus for calls that
    # never reached a Dial (e.g. no business found), though those won't have a business anyway.
    call_status = params.get("DialCallStatus") or params.get("CallStatus")
    to_number = params.get("To")
    from_number = params.get("From")

    if not (call_sid and call_status and to_number and from_number):
        return PlainTextResponse("missing required fields", status_code=400)

    business = db.query(Business).filter(Business.twilio_number == to_number).first()
    if business:
        handle_call_status(db, business, call_sid, from_number, call_status)

    return PlainTextResponse("ok")
