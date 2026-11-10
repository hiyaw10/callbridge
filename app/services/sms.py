import logging
import uuid

from fastapi import Request
from sqlalchemy.orm import Session
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import (
    CUSTOMER_TEXTS_ENABLED,
    OWNER_TEXT_FROM_NUMBER,
    PUBLIC_BASE_URL,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
)
from app.models import Business, TextMessage

logger = logging.getLogger("callbridge")

_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None


def send_sms(
    db: Session,
    business: Business,
    to_number: str,
    body: str,
    call_id: int | None = None,
    broadcast_id: int | None = None,
    request: Request | None = None,
    audience: str = "customer",
) -> TextMessage | None:
    """audience is "owner" for texts CallBridge sends to the business owner (sent from the
    verified CallBridge number) or "customer" for texts to the business's callers and
    customers, which are paused unless CUSTOMER_TEXTS_ENABLED is set. Returns None when a
    customer text is paused."""
    if audience == "customer" and not CUSTOMER_TEXTS_ENABLED:
        logger.info("Customer texts are paused, not sending to %s for business %s", to_number, business.id)
        return None
    from_number = (OWNER_TEXT_FROM_NUMBER if audience == "owner" else "") or business.twilio_number
    error_code = None
    if _client:
        # Accepting the send only means Twilio queued it — the carrier can still bounce it
        # (e.g. unverified toll-free number). status_callback lets /webhooks/twilio/sms-status
        # correct the record once Twilio knows the real outcome, instead of leaving it "sent" forever.
        # request is None when called from a standalone cron script (no live HTTP request to
        # derive a URL from) — PUBLIC_BASE_URL is the configured fallback for that case.
        base_url = str(request.base_url).rstrip("/") if request is not None else PUBLIC_BASE_URL
        status_callback = f"{base_url}/webhooks/twilio/sms-status" if base_url else None
        try:
            create_kwargs = {"to": to_number, "from_": from_number, "body": body}
            if status_callback:
                create_kwargs["status_callback"] = status_callback
            twilio_message = _client.messages.create(**create_kwargs)
            sid, status = twilio_message.sid, "sent"
        except TwilioRestException as exc:
            sid, status = None, "failed"
            error_code = str(exc.code) if exc.code is not None else None
    else:
        # No Twilio credentials configured (local dev) — simulate the send so the
        # rest of the flow (DB logging, dashboard) can be exercised without a live account.
        sid, status = f"SIMULATED-{uuid.uuid4().hex[:12]}", "sent"
        print(f"[sms:simulated] to={to_number} from={from_number} body={body!r}")

    message = TextMessage(
        business_id=business.id,
        call_id=call_id,
        broadcast_id=broadcast_id,
        direction="outbound",
        body=body,
        status=status,
        error_code=error_code,
        twilio_message_sid=sid,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
