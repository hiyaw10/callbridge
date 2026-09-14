import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./callbridge.db")
# Some providers (older Heroku/Railway conventions) still hand out "postgres://",
# which SQLAlchemy 2.0 rejects — it requires "postgresql://".
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

DEV_DEFAULT_ADMIN_TOKEN = "dev-admin-token"
DEV_DEFAULT_SECRET_KEY = "dev-secret-change-in-production"

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", DEV_DEFAULT_ADMIN_TOKEN)

SECRET_KEY = os.environ.get("SECRET_KEY", DEV_DEFAULT_SECRET_KEY)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")

# Used by send_sms to build the Twilio delivery-status callback URL when there's no live
# request to derive it from (scripts/review_requests.py, scripts/weekly_summary.py — both run
# standalone via cron, outside a web request). e.g. https://callbridge-production-xxxx.up.railway.app
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
