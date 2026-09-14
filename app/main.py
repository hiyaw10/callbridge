import logging

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import (
    ADMIN_TOKEN,
    DEV_DEFAULT_ADMIN_TOKEN,
    DEV_DEFAULT_SECRET_KEY,
    ENVIRONMENT,
    PUBLIC_BASE_URL,
    SECRET_KEY,
    SENTRY_DSN,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
)
from app.db import SessionLocal
from app.rate_limit import limiter
from app.routers import admin, auth, dashboard, webhooks
from app.templates_env import templates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("callbridge")

IS_PRODUCTION = ENVIRONMENT == "production"

if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, environment=ENVIRONMENT, traces_sample_rate=0.0)

fastapi_app = FastAPI(
    title="CallBridge",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

fastapi_app.state.limiter = limiter
fastapi_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

fastapi_app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=IS_PRODUCTION)
fastapi_app.mount("/static", StaticFiles(directory="app/static"), name="static")

fastapi_app.include_router(auth.router)
fastapi_app.include_router(dashboard.router)
fastapi_app.include_router(webhooks.router)
fastapi_app.include_router(admin.router)


@fastapi_app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@fastapi_app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    if SENTRY_DSN:
        sentry_sdk.capture_exception(exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@fastapi_app.get("/")
def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html")


@fastapi_app.get("/legal/opt-in-policy")
def opt_in_policy(request: Request):
    return templates.TemplateResponse(request, "opt_in_policy.html")


@fastapi_app.get("/health")
def health():
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        logger.exception("Health check failed")
        return JSONResponse(status_code=503, content={"status": "error"})
    return {"status": "ok"}


@fastapi_app.on_event("startup")
def check_production_config():
    if not IS_PRODUCTION:
        return
    problems = []
    if SECRET_KEY == DEV_DEFAULT_SECRET_KEY:
        problems.append("SECRET_KEY is still the dev default")
    if ADMIN_TOKEN == DEV_DEFAULT_ADMIN_TOKEN:
        problems.append("ADMIN_TOKEN is still the dev default")
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        problems.append(
            "TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN are not set — SMS sends will be simulated and "
            "Twilio webhook signature validation will be skipped (unauthenticated webhook)"
        )
    if not PUBLIC_BASE_URL:
        problems.append(
            "PUBLIC_BASE_URL is not set — review-request and weekly-summary texts (sent via "
            "cron, not a web request) won't get Twilio delivery-status tracking, so a failed "
            "send from those scripts will show as \"sent\" on the dashboard forever"
        )
    if problems:
        logger.warning(
            "Running with ENVIRONMENT=production but found configuration problems: %s",
            "; ".join(problems),
        )


# ProxyHeadersMiddleware must wrap the app last: Railway (and most PaaS proxies) terminate TLS
# at the edge and forward to this app over plain HTTP, setting X-Forwarded-Proto/X-Forwarded-For.
# Without trusting those headers, request.url reports "http://" even in production, which breaks
# Twilio's webhook signature validation (it signs the https:// URL it actually called).
app = ProxyHeadersMiddleware(fastapi_app, trusted_hosts="*")
