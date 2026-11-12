from fastapi import Request
from sqlalchemy.orm import Session

from app.models import Business, Call, PendingAmdResult
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
# "unknown" is deliberately NOT mapped here: it means AMD couldn't tell human from machine
# within its timeout (short greeting, brief pause, noisy audio) — it is not evidence of
# voicemail. Treating it as "missed" was misclassifying real human pickups as missed calls
# (and texting the customer a "sorry we missed you" while the owner was just on with them).
# Leaving it out of the map falls through to the plain completed->answered guess instead.
ANSWERED_BY_MAP = {
    "human": "answered",
    "machine_start": "missed",
    "machine_end_beep": "missed",
    "machine_end_silence": "missed",
    "machine_end_other": "missed",
    "fax": "missed",
}


# A dialed leg that connected for less than this many seconds, with no human verdict from
# Answering Machine Detection, is treated as missed. Carrier voicemail often picks up right at
# the end of our ring window and the caller hangs up on the greeting a moment later: Twilio calls
# that leg "completed" (answered) and AMD runs out of audio and reports "unknown", so the call
# looked answered when nobody spoke to the owner. A real conversation lasts longer than this, and
# a genuine human pickup is still caught by AMD's "human" verdict regardless of length.
SHORT_PICKUP_SECONDS = 8


def alert_owner_of_missed_call(
    db: Session, business: Business, caller_number: str, request: Request | None = None
) -> None:
    """Texts the business owner that a call was missed, from the verified CallBridge number.
    Deliberately not linked to the Call row: that link is what shows a message in the call's
    customer thread on the dashboard, and this one only goes to the owner."""
    if not business.owner_phone:
        return
    body = f"CallBridge: missed call from {caller_number}. Tap to call back. Reply STOP to opt out."
    send_sms(db, business, business.owner_phone, body, request=request, audience="owner")


def handle_call_status(
    db: Session,
    business: Business,
    call_sid: str,
    caller_number: str,
    twilio_call_status: str,
    answered_by: str | None = None,
    dial_call_sid: str | None = None,
    request: Request | None = None,
    dial_call_duration: int | None = None,
) -> Call | None:
    existing = db.query(Call).filter(Call.twilio_call_sid == call_sid).first()
    if existing:
        return existing  # webhook retry — already logged, don't double-text

    # AMD is asynchronous (see MACHINE_DETECTION_TIMEOUT_SECONDS in webhooks.py) and reports
    # to a separate callback keyed by the dialed leg's SID, which can arrive before this Dial
    # action callback does. If it already showed up, prefer it over a bare completed->answered
    # guess — that guess is exactly what misclassified voicemail as answered before.
    pending = None
    if answered_by is None and dial_call_sid:
        pending = db.query(PendingAmdResult).filter(PendingAmdResult.dial_call_sid == dial_call_sid).first()
        if pending:
            answered_by = pending.answered_by

    mapped_status = ANSWERED_BY_MAP.get(answered_by) if answered_by else None
    if mapped_status is None:
        mapped_status = TERMINAL_STATUS_MAP.get(twilio_call_status)
        if (
            mapped_status == "answered"
            and dial_call_duration is not None
            and dial_call_duration < SHORT_PICKUP_SECONDS
        ):
            mapped_status = "missed"
    if mapped_status is None:
        return None

    call = Call(
        business_id=business.id,
        caller_number=caller_number,
        status=mapped_status,
        twilio_call_sid=call_sid,
        dial_call_sid=dial_call_sid,
    )
    db.add(call)
    if pending:
        db.delete(pending)
    db.commit()
    db.refresh(call)

    if mapped_status == "missed":
        alert_owner_of_missed_call(db, business, caller_number, request)
        body = render_missed_call_message(business)
        send_sms(db, business, caller_number, body, call_id=call.id, request=request)

    return call


def apply_amd_result(
    db: Session, dial_call_sid: str, answered_by: str, request: Request | None = None
) -> Call | None:
    """Handles the async AMD status callback. If the Dial action callback already logged this
    call, corrects its status (and sends the missed-call text if AMD reveals it was actually
    voicemail/fax/unknown, not the human answer we'd assumed). If the call hasn't been logged
    yet, stashes the result for handle_call_status to pick up when it does."""
    call = db.query(Call).filter(Call.dial_call_sid == dial_call_sid).first()
    if call is None:
        db.merge(PendingAmdResult(dial_call_sid=dial_call_sid, answered_by=answered_by))
        db.commit()
        return None

    new_status = ANSWERED_BY_MAP.get(answered_by)
    if new_status is None or new_status == call.status:
        return call

    call.status = new_status
    db.add(call)
    db.commit()
    db.refresh(call)

    if new_status == "missed" and not call.text_messages:
        business = db.query(Business).filter(Business.id == call.business_id).first()
        alert_owner_of_missed_call(db, business, call.caller_number, request)
        body = render_missed_call_message(business)
        send_sms(db, business, call.caller_number, body, call_id=call.id, request=request)

    return call
