# CallBridge

Missed-call text-back for small trade and local service businesses (plumbers,
electricians, HVAC, auto shops, salons, vets, chiropractors, etc.). When a
call to a business's line goes unanswered, CallBridge automatically texts
the caller back, logs the conversation, and follows up with a review
request once a job is marked done.

## Tech stack

- **Backend**: FastAPI, synchronous routes (no async/await)
- **Database**: SQLite locally, Postgres in production — same SQLAlchemy
  models and queries either way, switching is a one-line `DATABASE_URL`
  change
- **Migrations**: Alembic (`render_as_batch=True` so SQLite ALTERs work)
- **SMS/Voice**: Twilio — call-status webhook for missed-call detection,
  Messaging API for SMS
- **Frontend**: server-rendered Jinja2 templates, no JS framework
- **Auth**: signed session cookies (Starlette `SessionMiddleware`) +
  `passlib`/bcrypt password hashing

## Project structure

```
app/
  main.py              FastAPI app, mounts routers + static files
  config.py             Env-var settings
  db.py                 Engine/session/Base
  models.py              SQLAlchemy models (Business, Call, TextMessage, Job)
  auth.py                 Password hashing, session dependencies
  routers/
    auth.py               Login, logout, forgot/reset password
    dashboard.py           Owner dashboard, jobs, two-way reply, settings
    webhooks.py             Twilio call-status webhook
    admin.py                 Internal-only "add a business" form
  services/
    sms.py                  Twilio send wrapper (simulated when no creds set)
    missed_call.py            Missed-call detection + auto text-back
    templates.py               Editable message-template rendering
  templates/              Jinja2 HTML templates
  static/style.css        Shared design system
scripts/
  seed.py                  Local dev seed data
  fake_twilio_webhook.py    Simulate a Twilio call-status POST
  review_requests.py         Cron: review-request texts, 24h after job done
  weekly_summary.py           Cron: weekly missed-call summary to the owner
alembic/                  Migrations
```

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # defaults work as-is for local dev

alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload
```

Visit `http://localhost:8000`. Log in with the seeded demo account printed
by `seed.py` (`owner@example.com` / `password123`).

Without real Twilio credentials set, SMS sends are simulated — logged to
the console instead of actually sent — so the whole flow (missed call →
auto text-back → dashboard → reply → job → review request) can be tested
end-to-end with no live Twilio account.

### Simulating a missed call

```bash
python scripts/fake_twilio_webhook.py --status no-answer
```

See `--help` for overriding the caller/business number or `CallSid` (reuse
a `--sid` to test idempotency — a repeated webhook shouldn't double-log or
double-text).

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `sqlite:///./callbridge.db` locally; Postgres URL in prod |
| `SECRET_KEY` | Session-cookie signing key |
| `ENVIRONMENT` | `development` shows local-only debug hints (demo login, reset-code fallback); set to `production` on Railway |
| `ADMIN_TOKEN` | Shared secret gating `/admin` (add-business form) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | Leave blank locally to simulate SMS and skip webhook signature validation. Set both to go live. |

## Adding a business

No self-serve signup yet — businesses are provisioned at `/admin/businesses`
(behind `ADMIN_TOKEN`, not tied to any customer login).

## Cron scripts

Not scheduled by the app itself — wire these up as scheduled jobs in
production (e.g. Railway's cron/scheduled service):

- `scripts/review_requests.py` — every ~15 minutes
- `scripts/weekly_summary.py` — weekly

## Deploying

1. Set the environment variables above (real values) on the host.
2. Run `alembic upgrade head` as a release step.
3. Point each business's Twilio number's Voice status-callback URL at
   `https://<domain>/webhooks/twilio/call-status`.
4. Schedule the two cron scripts above.
