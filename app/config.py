import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./callbridge.db")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "dev-admin-token")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
