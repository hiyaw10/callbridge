from fastapi import Request
from sqlalchemy.orm import Session

from app.models import Business, Call
from app.services.sms import send_sms
from app.services.templates import render_missed_call_message

# Twilio's terminal CallStatus values mapped to our Call.status. Used only when Answering
# Machine Detection didn't produce a result (see ANSWERED_BY_MAP below, which takes priority).
# 'failed' and any non-terminal status (queued/ringing/in-progress) are skipped —
# a failed call never really connected (bad number/carrier issue), not a missed customer call.
TERMINAL_STATUS_MAP = {
    "completed": "answered",
    "no-answer": "missed",
    "busy": "missed",
    "canceled": "missed",
}

# AnsweredBy comes from Twilio's Answering Machine Detection (AMD) on the owner's leg.
# Voicemail commonly picks up within our Dial timeout, which makes DialCallStatus report
# "completed" even though the owner never actually took the call — AMD is what tells the
# two cases apart, so it overrides the plain completed->answered mapping above.
ANSWERED_BY_MAP = {
    "human": "answered",
    "machine_start": "missed",
    "machine_end_beep": "missed",
    "machine_end_silence": "missed",
    "machine_end_other": "missed",
    "fax": "missed",
    "unknown": "missed",
}


def handle_call_status(
    db: Session,
    business: Business,
    call_sid: str,
    caller_number: str,
    twilio_call_status: str,
    answered_by: str | None = None,
    request: Request | None = None,
) -> Call | None:
    mapped_status = ANSWERED_BY_MAP.get(answered_by) if answered_by else None
    if mapped_status is None:
        mapped_status = TERMINAL_STATUS_MAP.get(twilio_call_status)
    if mapped_status is None:
        return None

    existing = db.query(Call).filter(Call.twilio_call_sid == call_sid).first()
    if existing:
        return existing  # webhook retry — already logged, don't double-text

    call = Call(
        business_id=business.id,
        caller_number=caller_number,
        status=mapped_status,
        twilio_call_sid=call_sid,
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    if mapped_status == "missed":
        body = render_missed_call_message(business)
        send_sms(db, business, caller_number, body, call_id=call.id, request=request)

    return call
