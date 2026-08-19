import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password
from app.db import SessionLocal
from app.models import Business, Call, Job, TextMessage
from app.services.templates import render_missed_call_message

SEED_EMAIL = "owner@example.com"
SEED_PASSWORD = "password123"


def main():
    db = SessionLocal()
    try:
        existing = db.query(Business).filter(Business.owner_email == SEED_EMAIL).first()
        if existing:
            print(f"Already seeded: {SEED_EMAIL} (business id={existing.id}, twilio_number={existing.twilio_number})")
            return

        business = Business(
            name="Riverside Home Services",
            owner_email=SEED_EMAIL,
            owner_phone="+15555550100",
            password_hash=hash_password(SEED_PASSWORD),
            twilio_number="+15555550123",
            plan_tier="starter",
            billing_cycle="monthly",
        )
        db.add(business)
        db.commit()
        db.refresh(business)

        call = Call(
            business_id=business.id,
            caller_number="+15555550199",
            status="missed",
            twilio_call_sid="SEED-CALL-1",
        )
        db.add(call)
        db.commit()
        db.refresh(call)

        db.add(
            TextMessage(
                business_id=business.id,
                call_id=call.id,
                direction="outbound",
                body=render_missed_call_message(business),
                status="sent",
                twilio_message_sid="SEED-MSG-1",
            )
        )
        db.add(Job(business_id=business.id, customer_phone="+15555550188", completed_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.add(Job(business_id=business.id, customer_phone="+15555550177"))
        db.commit()

        print("Seeded business:")
        print(f"  email:         {SEED_EMAIL}")
        print(f"  password:      {SEED_PASSWORD}")
        print(f"  twilio_number: {business.twilio_number}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
