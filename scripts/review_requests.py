"""Cron script: text customers a review request 24h after their job is marked done.

Run on a schedule (e.g. every 15 min) via Railway's cron/scheduled service:
    python scripts/review_requests.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.models import Business, Job
from app.services.sms import send_sms
from app.services.templates import render_review_request_message


def main():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=24)

    db = SessionLocal()
    try:
        due_jobs = (
            db.query(Job)
            .filter(Job.completed_at <= cutoff, Job.review_text_sent_at.is_(None))
            .all()
        )

        sent = 0
        for job in due_jobs:
            business = db.get(Business, job.business_id)
            if not business:
                continue
            body = render_review_request_message(business)
            send_sms(db, business, job.customer_phone, body)
            job.review_text_sent_at = now
            db.add(job)
            sent += 1

        db.commit()
        print(f"Sent {sent} review request text(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
