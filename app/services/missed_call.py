from sqlalchemy.orm import Session

from app.models import Business, Call
from app.services.sms import send_sms
from app.services.templates import render_missed_call_message

# Twilio's terminal CallStatus values mapped to our Call.status.
# 'failed' and any non-terminal status (queued/ringing/in-progress) are skipped —
# a failed call never really connected (bad number/carrier issue), not a missed customer call.
TERMINAL_STATUS_MAP = {
    "completed": "answered",
    "no-answer": "missed",
    "busy": "missed",
    "canceled": "missed",
}


def handle_call_status(
    db: Session, business: Business, call_sid: str, caller_number: str, twilio_call_status: str
) -> Call | None:
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
        send_sms(db, business, caller_number, body, call_id=call.id)

    return call
