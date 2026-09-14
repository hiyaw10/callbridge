import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from app.config import TWILIO_AUTH_TOKEN
from app.db import get_db
from app.models import Business, TextMessage
from app.services.missed_call import apply_amd_result, handle_call_status

logger = logging.getLogger("callbridge")

router = APIRouter()

# How long to ring the owner's phone before treating the call as missed.
DIAL_TIMEOUT_SECONDS = 15

# Answering Machine Detection: without this, carrier voicemail picking up within the Dial
# timeout above makes Twilio report the call as "completed" (i.e. answered) even though the
# owner never touched it. AMD analyzes the pickup audio and reports the human/machine result
# to amd_status_callback below — Twilio's own warning 21262 confirms that without an explicit
# callback URL, AMD does not reliably report back at all (it needs somewhere to post the
# result to), so we can't rely on AnsweredBy just showing up on the Dial action callback.
MACHINE_DETECTION_TIMEOUT_SECONDS = 10


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
        base_url = str(request.base_url).rstrip("/")
        dial = response.dial(
            timeout=DIAL_TIMEOUT_SECONDS, action=f"{base_url}/webhooks/twilio/call-status", method="POST"
        )
        dial.number(
            business.owner_phone,
            machine_detection="Enable",
            machine_detection_timeout=MACHINE_DETECTION_TIMEOUT_SECONDS,
            amd_status_callback=f"{base_url}/webhooks/twilio/amd-status",
            amd_status_callback_method="POST",
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
    # AnsweredBy normally is NOT present here — AMD is async (see amd_status_callback above)
    # and reports separately to /amd-status, possibly before this webhook even arrives.
    answered_by = params.get("AnsweredBy")
    # SID of the dialed leg (distinct from CallSid, which is the parent/inbound call) — lets
    # a same- or later-arriving AMD result find its way back to this Call row.
    dial_call_sid = params.get("DialCallSid")
    to_number = params.get("To")
    from_number = params.get("From")

    if not (call_sid and call_status and to_number and from_number):
        return PlainTextResponse("missing required fields", status_code=400)

    business = db.query(Business).filter(Business.twilio_number == to_number).first()
    call = None
    if business:
        call = handle_call_status(
            db, business, call_sid, from_number, call_status, answered_by, dial_call_sid, request
        )

    logger.info(
        "call-status webhook: call_sid=%s dial_call_sid=%s from=%s to=%s call_status=%s "
        "answered_by=%s business_found=%s mapped_status=%s",
        call_sid, dial_call_sid, from_number, to_number, call_status, answered_by,
        bool(business), call.status if call else None,
    )

    return PlainTextResponse("ok")


@router.post("/webhooks/twilio/amd-status")
async def twilio_amd_status(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    params = dict(form)

    if not _validate_twilio_request(request, params):
        return PlainTextResponse("invalid signature", status_code=403)

    # This callback reports on the DIALED leg, so its CallSid is what call-status calls
    # DialCallSid, not the parent call's CallSid.
    dial_call_sid = params.get("CallSid")
    answered_by = params.get("AnsweredBy")

    if not (dial_call_sid and answered_by):
        return PlainTextResponse("missing required fields", status_code=400)

    call = apply_amd_result(db, dial_call_sid, answered_by, request)

    logger.info(
        "amd-status webhook: dial_call_sid=%s answered_by=%s resulting_status=%s",
        dial_call_sid, answered_by, call.status if call else "(call not yet logged, stashed)",
    )

    return PlainTextResponse("ok")


# Twilio's outbound SMS statuses, in order: queued -> sending -> sent -> delivered, or
# undelivered/failed if the carrier or Twilio itself rejects it (e.g. an unverified toll-free
# number, error 30032). We only care about the terminal outcomes here — the initial "sent" is
# already recorded synchronously by send_sms when the API call is accepted.
_TERMINAL_SMS_STATUSES = {"delivered", "undelivered", "failed"}


@router.post("/webhooks/twilio/sms-status")
async def twilio_sms_status(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    params = dict(form)

    if not _validate_twilio_request(request, params):
        return PlainTextResponse("invalid signature", status_code=403)

    message_sid = params.get("MessageSid")
    message_status = params.get("MessageStatus")
    error_code = params.get("ErrorCode")

    if not (message_sid and message_status):
        return PlainTextResponse("missing required fields", status_code=400)

    if message_status in _TERMINAL_SMS_STATUSES:
        message = db.query(TextMessage).filter(TextMessage.twilio_message_sid == message_sid).first()
        if message:
            message.status = message_status
            message.error_code = error_code
            db.add(message)
            db.commit()

    return PlainTextResponse("ok")
