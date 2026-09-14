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
| `DATABASE_URL` | `sqlite:///./callbridge.db` locally; Postgres URL in prod. A `postgres://` prefix (some providers still use it) is auto-rewritten to `postgresql://`, which SQLAlchemy 2.0 requires. |
| `SECRET_KEY` | Session-cookie signing key. **Must** be a long random value in prod — the app logs a startup warning if it's still the dev default. |
| `ENVIRONMENT` | `development` shows local-only debug hints (demo login, reset-code fallback) and enables `/docs`. Set to `production` on Railway — this also makes session cookies HTTPS-only and disables `/docs`/`/redoc`/`/openapi.json`. |
| `ADMIN_TOKEN` | Shared secret gating `/admin` (add-business form). **Must** be a long random value in prod. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | Leave blank locally to simulate SMS and skip webhook signature validation. Set both to go live — required in prod, or webhooks are unauthenticated. |
| `PUBLIC_BASE_URL` | Your production URL (e.g. `https://your-app.up.railway.app`), no trailing slash. Used to register Twilio's SMS delivery-status callback for texts sent by `scripts/review_requests.py` / `scripts/weekly_summary.py`, which run via cron with no live request to derive the URL from. Without it, a failed send from those scripts shows as "sent" on the dashboard forever instead of self-correcting to undelivered/failed. |
| `SENTRY_DSN` | Optional. If set, unhandled errors are reported to Sentry in addition to logs. |

The app checks these on startup when `ENVIRONMENT=production` and logs a
warning (not a hard crash) if any are missing or still set to dev defaults —
check the logs right after deploying.

## Production hardening already in place

- **Proxy headers**: Railway (and most PaaS) terminate TLS at the edge and
  forward over plain HTTP. The app trusts `X-Forwarded-Proto` so
  `request.url` — and therefore Twilio's webhook signature check — sees the
  real `https://` scheme instead of failing every request.
- **Rate limiting**: `/login` (10/min), `/forgot-password` (5/min), and
  `/reset-password` (10/min) are rate-limited per IP.
- **Reset-code lockout**: a password-reset code is invalidated after 5
  wrong guesses, independent of its 15-minute expiry.
- **Secure cookies**: session cookies are HTTPS-only when
  `ENVIRONMENT=production`.
- **`/health`**: pings the database, returns 503 if it can't connect — point
  Railway's health check (or an uptime monitor) at this.
- **Global error handler**: unhandled exceptions are logged server-side
  (and sent to Sentry if configured) without leaking a stack trace to the
  client.

## Adding a business

No self-serve signup yet — businesses are provisioned at `/admin/businesses`
(behind `ADMIN_TOKEN`, not tied to any customer login).

## Cron scripts

Not scheduled by the app itself — wire these up as scheduled jobs in
production (e.g. Railway's cron/scheduled service):

- `scripts/review_requests.py` — every ~15 minutes
- `scripts/weekly_summary.py` — weekly

## Deploying (Railway)

1. **Create the Railway project** from this GitHub repo, and add a Postgres
   database to it (Railway sets `DATABASE_URL` automatically for the web
   service when you add its Postgres plugin).
2. **Set environment variables** on the web service (Railway → Variables):
   - `ENVIRONMENT=production`
   - `SECRET_KEY` — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `ADMIN_TOKEN` — generate the same way
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` — from the Twilio Console
   - `PUBLIC_BASE_URL` — your Railway domain, e.g. `https://your-app.up.railway.app`
     (also set this on the two cron jobs in step 7 — they share the same env vars
     as the web service by default, but confirm it's there)
   - `SENTRY_DSN` — optional, from sentry.io if you want error alerts
   - Do **not** set `DATABASE_URL` yourself if Railway's Postgres plugin
     already provides it.
3. **Start command**: the included `Procfile` (`alembic upgrade head &&
   uvicorn app.main:app --host 0.0.0.0 --port $PORT`) runs migrations
   before every boot — Railway picks this up automatically. If it doesn't,
   set it explicitly as the service's start command.
4. **Deploy**, then check the deploy logs for the startup warning line — it
   tells you if any of the variables above are missing.
5. **Health check**: point Railway's health check (Settings → Healthcheck
   Path) at `/health`.
6. **Twilio webhook**: in the Twilio Console, on the phone number, set the
   Voice "Call status changes" webhook to
   `https://<your-railway-domain>/webhooks/twilio/call-status`.
7. **Cron jobs**: add two Railway Cron Jobs (or Scheduled Services) running
   in this same project so they share the database:
   - `python scripts/review_requests.py` — every 15 minutes: `*/15 * * * *`
   - `python scripts/weekly_summary.py` — weekly, e.g. Monday 8am: `0 8 * * 1`
8. **Add the first real business** at `/admin/businesses` (using
   `ADMIN_TOKEN`), with its real Twilio number.
9. **Test it for real**: call the number from your own phone, let it ring
   out, confirm the text arrives and shows up on the dashboard.
