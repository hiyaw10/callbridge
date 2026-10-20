<p align="center">
  <img src="app/static/brand/logo.png" alt="CallBridge" width="360">
</p>

CallBridge is a customer growth platform for service businesses: plumbers,
electricians, HVAC, auto shops, salons, vets, chiropractors, grocery stores,
and anyone else whose revenue depends on someone answering the phone.

When a call to a business's line goes unanswered, CallBridge texts the caller
back within seconds. From the same dashboard the owner can see every call and
reply, ask happy customers for Google reviews automatically, and send an
announcement to customers who have called or been served. Live at
[callbridgeapp.com](https://www.callbridgeapp.com).

## What it does

**For a business owner (the dashboard)**

- **Missed-call text-back.** An unanswered call triggers an automatic text
  from the business's own number. Voicemail pickups count as missed, and a
  short human pickup counts as answered (see [How a call is classified](#how-a-call-is-classified)).
- **Call and text log.** Every call, every automatic reply, and two-way
  replies from the owner, with filtering, search by number, and archive/restore.
- **Review requests.** Mark a job complete and a Google review request goes
  out 24 hours later.
- **Announcements.** One text to every customer who has called or had a job,
  minus anyone who replied STOP, with a history of what was sent and how it
  landed.
- **Weekly summary.** A text each week with how many calls were missed and
  covered.
- **Settings.** Editable message templates and the business's time zone.

**For the CallBridge team (the admin panel at `/admin`)**

- **Analytics.** Active businesses, estimated MRR, lead counts, weekly growth
  (searchable, paginated), and platform-wide call, text, job, and announcement
  activity with a date-range filter. Archived businesses and leads are
  excluded from every figure.
- **Leads.** Everyone who filled out the "Book a Free Call" form, with search,
  internal remarks, archive/restore, and pagination.
- **Businesses.** Create and edit client accounts and Twilio numbers, with the
  same search, remarks, archive/restore, and pagination.

**For prospects (the public site)**

- A landing page, a lead-capture funnel (`/book-a-call` records the prospect,
  then hands off to Calendly with name and email prefilled), and an
  [opt-in and consent policy](app/templates/opt_in_policy.html) page at
  `/legal/opt-in-policy`.

## How a call is classified

1. Twilio hits `POST /webhooks/twilio/voice`. The app looks the business up by
   the dialed number and returns TwiML that rings the owner's phone for 15
   seconds with Answering Machine Detection (AMD) enabled.
2. When the dial ends, Twilio posts the outcome to `/webhooks/twilio/call-status`
   (`completed`, `no-answer`, `busy`, `canceled`). AMD reports separately and
   asynchronously to `/webhooks/twilio/amd-status`, and either callback can
   arrive first.
3. `app/services/missed_call.py` combines the two: a confirmed machine or fax
   pickup is missed, a confirmed human is answered, and an inconclusive AMD
   result (`unknown`, common on a very short pickup) falls back to the dial
   outcome instead of guessing "missed". Missed calls get the text-back.

Retries are safe: each call is keyed by its Twilio SID, so a repeated webhook
never double-logs or double-texts.

## Tech stack

- **Backend**: FastAPI, synchronous routes
- **Database**: SQLite locally, Postgres in production (same SQLAlchemy models,
  one `DATABASE_URL` change)
- **Migrations**: Alembic (`render_as_batch=True` so SQLite ALTERs work)
- **Voice and SMS**: Twilio (voice webhook with AMD, Messaging API, delivery
  status and inbound SMS webhooks)
- **Frontend**: server-rendered Jinja2 templates, plain CSS design system, no
  JS framework
- **Auth**: signed session cookies (Starlette `SessionMiddleware`), bcrypt via
  `passlib`, a shared `ADMIN_TOKEN` for the admin panel
- **Hosting**: Railway (web service, Postgres, cron jobs)
- **Analytics**: Google Analytics 4 for site traffic, when configured

## Project structure

```
app/
  main.py                FastAPI app, middleware, landing page, /health
  config.py              Env-var settings
  db.py                  Engine, session, Base
  models.py              Business, Call, TextMessage, Job, Broadcast, SmsOptOut,
                         Lead, PendingAmdResult
  auth.py                Password hashing, session and admin dependencies
  rate_limit.py          Per-IP rate limiting (slowapi)
  templates_env.py       Jinja environment, filters, template globals
  routers/
    auth.py              Login, logout, forgot and reset password
    dashboard.py         Owner dashboard, replies, jobs, announcements, settings
    webhooks.py          Twilio voice, call-status, AMD, SMS status, SMS inbound
    leads.py             /book-a-call lead capture, then Calendly handoff
    admin.py             Analytics, leads, and businesses (admin token required)
  services/
    missed_call.py      Call classification and auto text-back
    sms.py               Twilio send wrapper (simulated when no credentials set)
    templates.py         Editable message-template rendering
    localtime.py         UTC storage, per-business display time zones
  templates/             Jinja2 HTML
  static/
    style.css            Shared design system
    brand/               Logo variants, favicon, app icon, social share image
    photos/              Landing page photography
scripts/
  seed.py                        Local dev seed data
  fake_twilio_webhook.py         Simulate a Twilio call-status POST
  review_requests.py             Cron: review-request texts, 24h after a job is done
  weekly_summary.py              Cron: weekly summary text to each owner
alembic/                 Migrations
Procfile                 Runs migrations, then starts uvicorn
```

## Routes at a glance

| Area | Routes |
|---|---|
| Public | `/`, `/book-a-call`, `/legal/opt-in-policy`, `/health`, `/login`, `/forgot-password`, `/reset-password` |
| Owner (login required) | `/dashboard`, `/dashboard/broadcast`, `/dashboard/broadcasts`, `/dashboard/settings` |
| Admin (`ADMIN_TOKEN`) | `/admin/login`, `/admin/analytics`, `/admin/leads`, `/admin/businesses` |
| Twilio webhooks | `/webhooks/twilio/voice`, `/call-status`, `/amd-status`, `/sms-status`, `/sms-inbound` |

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

Visit `http://localhost:8000` and log in with the seeded demo account printed
by `seed.py` (`owner@example.com` / `password123`). The admin panel is at
`/admin/login` (default local token: `dev-admin-token`).

Without Twilio credentials, SMS sends are simulated (logged to the console)
and webhook signature checks are skipped, so the whole flow (missed call, text
back, dashboard, reply, job, review request, announcement) runs end to end
with no live account.

### Simulating a missed call

```bash
python scripts/fake_twilio_webhook.py --status no-answer
```

See `--help` for the caller, business number, and `--sid` options. Reusing a
`--sid` tests idempotency: a repeated webhook must not double-log or double-text.

## Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `sqlite:///./callbridge.db` locally, a Postgres URL in prod. A `postgres://` prefix is rewritten to `postgresql://` for SQLAlchemy 2.0. |
| `SECRET_KEY` | Session-cookie signing key. **Must** be a long random value in prod; a startup warning fires if it is still the dev default. |
| `ENVIRONMENT` | `development` shows local-only hints (such as the reset-code fallback) and enables `/docs`. `production` makes cookies HTTPS-only, disables `/docs`, `/redoc`, `/openapi.json`, and runs the startup config check. |
| `ADMIN_TOKEN` | Shared secret for `/admin`. **Must** be a long random value in prod. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | Blank locally to simulate SMS and skip signature validation. Set both to go live. In prod they are required, or webhooks are unauthenticated. |
| `PUBLIC_BASE_URL` | The deployment's public URL, no trailing slash. Used to register SMS delivery-status callbacks for texts sent by the cron scripts, which have no live request to derive it from. |
| `LEGAL_ENTITY_NAME` | The company name shown on the privacy policy and terms pages. Defaults to `CallBridge`; set it to the exact registered name (for example `CallBridge LLC`) once the company exists. |
| `CALENDLY_URL` | Where `/book-a-call` sends prospects after they submit. Defaults to the 30 minute event; point it at the event type the landing page promises. |
| `GA_MEASUREMENT_ID` | Google Analytics 4 ID (`G-XXXXXXXXXX`). The tracking tag only renders when this is set, so local and staging traffic never reach the real property. |
| `SENTRY_DSN` | Optional. Reports unhandled errors to Sentry in addition to logs. |

With `ENVIRONMENT=production` the app checks these on startup and logs a
warning (not a crash) for anything missing or still at a dev default. Check the
logs right after each deploy.

## Twilio configuration

On each business's phone number in the Twilio Console:

| Setting | Value |
|---|---|
| Voice, **A call comes in** | Webhook, `POST`, `https://<domain>/webhooks/twilio/voice` |
| Messaging, **A message comes in** | Webhook, `POST`, `https://<domain>/webhooks/twilio/sms-inbound` (records STOP and START so announcements honor opt-outs) |

The call-status, AMD, and SMS delivery-status callbacks do not need to be set in
the console: the app registers them per call and per message, using the domain
the request arrived on. Use your **custom domain** (or a stable Railway domain)
in these URLs. A generated `*.up.railway.app` domain that gets recreated will
silently break call forwarding.

US toll-free numbers must be verified with Twilio before carriers reliably
deliver messages. Unverified sends fail with error `30032`, which the dashboard
shows as a failed text rather than a success.

## Branches and environments

| Branch | Environment | Purpose |
|---|---|---|
| `main` | Production | What customers use. Deploys automatically. Treat as always releasable. |
| `staging` | Staging | Pre-production. Every change lands here first, is checked against a real Railway deploy, then is promoted. |

Workflow once the business is live:

1. Branch from `staging`: `git checkout staging && git pull && git checkout -b feat/my-change`.
2. Open a pull request into `staging`. Merging it deploys to the staging environment.
3. Verify there (real deploy, real Postgres, a test Twilio number).
4. Open a pull request from `staging` into `main` to release.
5. Hotfixes may branch from `main`, but merge the fix back into `staging` afterward so the branches don't drift.

### Setting up the Railway staging environment

1. In the Railway project, create a new **environment** named `staging` (duplicating `production` copies the services and variables).
2. Set the staging web service to deploy from the `staging` branch. Production stays on `main`.
3. Staging gets its **own** Postgres (never point it at production data).
4. Staging variables: `ENVIRONMENT=production` (so it behaves like prod), a **different** `SECRET_KEY` and `ADMIN_TOKEN`, `PUBLIC_BASE_URL` set to the staging domain, and `GA_MEASUREMENT_ID` **left empty** so test traffic stays out of analytics.
5. Use a **separate Twilio number** for staging, with its webhooks pointed at the staging domain. Never point production's number at staging.
6. Recreate the two cron jobs in the staging environment against the staging database, or leave them off.

## Deploying (Railway)

1. **Create the Railway project** from this GitHub repo and add a Postgres
   database (Railway sets `DATABASE_URL` for the web service).
2. **Set environment variables** on the web service:
   `ENVIRONMENT=production`, `SECRET_KEY` and `ADMIN_TOKEN`
   (generate each with `python3 -c "import secrets; print(secrets.token_hex(32))"`),
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `PUBLIC_BASE_URL`,
   `GA_MEASUREMENT_ID` and `SENTRY_DSN` if used, and `CALENDLY_URL` if it
   differs from the default. Do **not** set `DATABASE_URL` yourself when the
   Postgres plugin provides it.
3. **Start command**: the `Procfile` runs `alembic upgrade head` before every
   boot, then starts uvicorn.
4. **Health check**: set Railway's health check path to `/health`.
5. **Custom domain**: attach it to the service and use it in every Twilio
   webhook URL (see above).
6. **Twilio**: configure the number as described in
   [Twilio configuration](#twilio-configuration).
7. **Cron jobs**: two Railway cron services in the same project, sharing the
   database:
   - `python scripts/review_requests.py` every 15 minutes (`*/15 * * * *`)
   - `python scripts/weekly_summary.py` weekly (`0 8 * * 1`)
8. **Add the first business** at `/admin/businesses` with its real Twilio number.
9. **Test for real**: call the number from your own phone, let it ring out,
   confirm the text arrives and the call appears on the dashboard. Then answer
   one and confirm it is logged as answered.

There is no self-serve signup: businesses are provisioned by an admin after an
onboarding call.

## Working on the code

- **Migrations**: after changing `app/models.py`, run
  `alembic revision -m "what changed"`, fill in `upgrade()` and `downgrade()`,
  then verify a full round trip on a throwaway database before committing:
  `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`.
- **Branding**: the logo lives in `app/static/brand/` (`logo.png` for light
  backgrounds, `logo-light.png` for dark ones, plus icon, favicon, and
  `og-image.png` for link previews). The primary color in `style.css`
  (`--primary`) is the logo's navy; the gold accent is `--accent`.
- **Timestamps** are stored in UTC and displayed in each business's time zone
  (`localtime` filter).

## Production hardening already in place

- **Proxy headers**: TLS terminates at Railway's edge. The app trusts
  `X-Forwarded-Proto`, so `request.url` and Twilio's signature check see the
  real `https://` scheme.
- **Twilio signature validation** on every webhook when credentials are set.
- **Rate limiting**: `/login` (10/min), `/forgot-password` (5/min),
  `/reset-password` (10/min), `/book-a-call` (10/min), per IP.
- **Reset-code lockout**: a password-reset code is invalidated after 5 wrong
  guesses, independent of its 15 minute expiry.
- **Secure cookies** when `ENVIRONMENT=production`.
- **`/health`** pings the database and returns 503 if it cannot connect.
- **Global error handler**: unhandled exceptions are logged (and sent to Sentry
  if configured) without leaking a stack trace to the client.
- **Opt-out handling**: STOP replies are recorded per business and excluded from
  every announcement.
