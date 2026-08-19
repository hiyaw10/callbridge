import uuid

from sqlalchemy.orm import Session
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
from app.models import Business, TextMessage

_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None


def send_sms(db: Session, business: Business, to_number: str, body: str, call_id: int | None = None) -> TextMessage:
    if _client:
        try:
            twilio_message = _client.messages.create(to=to_number, from_=business.twilio_number, body=body)
            sid, status = twilio_message.sid, "sent"
        except TwilioRestException:
            sid, status = None, "failed"
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
        twilio_message_sid=sid,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
