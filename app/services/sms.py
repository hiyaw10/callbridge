import uuid

from fastapi import Request
from sqlalchemy.orm import Session
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
from app.models import Business, TextMessage

_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None


def send_sms(
    db: Session,
    business: Business,
    to_number: str,
    body: str,
    call_id: int | None = None,
    request: Request | None = None,
) -> TextMessage:
    error_code = None
    if _client:
        # Accepting the send only means Twilio queued it — the carrier can still bounce it
        # (e.g. unverified toll-free number). status_callback lets /webhooks/twilio/sms-status
        # correct the record once Twilio knows the real outcome, instead of leaving it "sent" forever.
        status_callback = None
        if request is not None:
            status_callback = str(request.base_url).rstrip("/") + "/webhooks/twilio/sms-status"
        try:
            create_kwargs = {"to": to_number, "from_": business.twilio_number, "body": body}
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
        print(f"[sms:simulated] to={to_number} from={business.twilio_number} body={body!r}")

    message = TextMessage(
        business_id=business.id,
        call_id=call_id,
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
