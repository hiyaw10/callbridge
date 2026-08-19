"""Cron script: text each business owner a weekly missed-call summary.

Run once a week (e.g. Monday morning) via Railway's cron/scheduled service:
    python scripts/weekly_summary.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.models import Business, Call
from app.services.sms import send_sms


def main():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    week_ago = now - timedelta(days=7)

    db = SessionLocal()
    try:
        businesses = db.query(Business).all()
        for business in businesses:
            missed_count = (
                db.query(Call)
                .filter(
                    Call.business_id == business.id,
                    Call.status == "missed",
                    Call.timestamp >= week_ago,
                )
                .count()
            )
            body = f"You missed {missed_count} call{'s' if missed_count != 1 else ''} this week."
            send_sms(db, business, business.owner_phone, body)

        db.commit()
        print(f"Sent {len(businesses)} weekly summary text(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
