import re
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import Business, Call, SmsOptOut, TextMessage
from app.services.sms import send_sms

# Only someone who actually called the business recently is treated as a customer replying.
# Anyone else who texts the number (wrong number, a stranger, spam) is ignored, so a stranger
# can't push messages onto an owner's dashboard or phone.
REPLY_WINDOW = timedelta(days=14)

# How much of the caller's reply is repeated in the text to the owner. The whole thing is on
# the dashboard; the text only needs to be enough to decide whether to call back now.
_FORWARD_SNIPPET_CHARS = 70


def record_caller_reply(
    db: Session,
    business: Business,
    from_number: str,
    body: str,
    message_sid: str | None,
    request: Request | None = None,
) -> bool:
    """Saves a customer's text reply on the call thread it answers and forwards it to the
    owner's phone. Returns True when the reply was recorded, False when it was ignored
    (not from a recent caller, or a webhook retry of a reply already saved)."""
    if message_sid and db.query(TextMessage.id).filter(TextMessage.twilio_message_sid == message_sid).first():
        return False  # Twilio retried the webhook — already saved and forwarded

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - REPLY_WINDOW
    call = (
        db.query(Call)
        .filter(
            Call.business_id == business.id,
            Call.caller_number == from_number,
            Call.timestamp >= cutoff,
        )
        .order_by(Call.timestamp.desc())
        .first()
    )
    if call is None:
        return False

    db.add(
        TextMessage(
            business_id=business.id,
            call_id=call.id,
            direction="inbound",
            body=body,
            status="delivered",
            twilio_message_sid=message_sid,
        )
    )
    db.commit()

    if business.owner_phone:
        snippet = " ".join(body.split()) or "(no text)"
        if len(snippet) > _FORWARD_SNIPPET_CHARS:
            snippet = snippet[: _FORWARD_SNIPPET_CHARS - 1].rstrip() + "…"
        forward = (
            f'CallBridge: {from_number} replied: "{snippet}" '
            f"Text back to answer, or start with #{from_number[-4:]} to pick this customer."
        )
        send_sms(db, business, business.owner_phone, forward, request=request, audience="owner")
    return True


def _digits(number: str | None) -> str:
    return re.sub(r"\D", "", number or "")


def is_owner_number(business: Business, from_number: str | None) -> bool:
    """True when a text came from the business owner's own phone (compared on the last ten
    digits, so +1 formatting differences don't matter)."""
    owner, sender = _digits(business.owner_phone), _digits(from_number)
    return len(owner) >= 10 and owner[-10:] == sender[-10:]


# "#8678 sounds good" picks the customer whose number ends in 8678.
_PICK_CUSTOMER = re.compile(r"^#(\d{4,10})\b[\s:,.-]*(.*)$", re.DOTALL)


def _notify_owner(db: Session, business: Business, text: str, request: Request | None) -> None:
    send_sms(db, business, business.owner_phone, f"CallBridge: {text}", request=request, audience="owner")


def route_owner_reply(
    db: Session, business: Business, raw_body: str, request: Request | None = None
) -> str:
    """The owner texting the CallBridge number answers a customer. The text goes to the customer
    who most recently replied, or to the one picked with "#1234 ..." (the last digits of their
    number). The owner is told when the text could not be delivered, and told who got it
    whenever more than one customer is waiting, so a reply never goes to the wrong person
    silently. Returns a short outcome label."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    message = raw_body.strip()
    pick = _PICK_CUSTOMER.match(message)
    if pick:
        digits, message = pick.group(1), pick.group(2).strip()
    else:
        digits = None
    if not message:
        return "empty"

    replies = (
        db.query(TextMessage)
        .filter(
            TextMessage.business_id == business.id,
            TextMessage.direction == "inbound",
            TextMessage.call_id.isnot(None),
            TextMessage.timestamp >= now - REPLY_WINDOW,
        )
        .order_by(TextMessage.timestamp.desc(), TextMessage.id.desc())
        .all()
    )
    # One entry per customer, most recent reply first.
    waiting: dict[str, TextMessage] = {}
    for reply in replies:
        call = db.query(Call).filter(Call.id == reply.call_id).first()
        if call and call.caller_number not in waiting:
            waiting[call.caller_number] = reply

    if digits:
        matches = [n for n in waiting if _digits(n).endswith(digits)]
        if not matches:
            # Not someone who replied: allow any recent caller of this business.
            recent = (
                db.query(Call.caller_number)
                .filter(Call.business_id == business.id, Call.timestamp >= now - REPLY_WINDOW)
                .distinct()
                .all()
            )
            matches = [n for (n,) in recent if _digits(n).endswith(digits)]
        if len(matches) != 1:
            _notify_owner(
                db, business,
                f"no customer matches #{digits}. Use more digits." if matches else f"no recent customer ends in {digits}.",
                request,
            )
            return "no_match" if not matches else "ambiguous"
        target = matches[0]
    else:
        if not waiting:
            _notify_owner(db, business, "no customer has replied yet. Call them, or answer from your dashboard.", request)
            return "nobody_waiting"
        target = next(iter(waiting))

    if db.query(SmsOptOut).filter(SmsOptOut.business_id == business.id, SmsOptOut.phone_number == target).first():
        _notify_owner(db, business, f"{target} opted out of texts, so your message was not sent. Call them instead.", request)
        return "opted_out"

    call = (
        db.query(Call)
        .filter(Call.business_id == business.id, Call.caller_number == target)
        .order_by(Call.timestamp.desc())
        .first()
    )
    sent = send_sms(db, business, target, message, call_id=call.id, request=request)
    if sent is None:
        _notify_owner(db, business, "texting customers is paused, so your message was not sent.", request)
        return "paused"
    if sent.status == "failed":
        _notify_owner(db, business, f"your message to {target} could not be delivered. Call them instead.", request)
        return "failed"

    day_ago = now - timedelta(hours=24)
    waiting_today = [n for n, r in waiting.items() if r.timestamp >= day_ago]
    if digits or len(waiting_today) > 1:
        _notify_owner(db, business, f"sent to {target}.", request)
    return "sent"
