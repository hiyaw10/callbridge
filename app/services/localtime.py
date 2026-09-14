from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import Business

UTC = ZoneInfo("UTC")
DEFAULT_TIMEZONE = "America/Chicago"  # Iowa (Central Time, DST-aware)

# Curated to the timezones a US local service business would actually need —
# offered as a dropdown in Settings rather than a free-text IANA name.
TIMEZONE_CHOICES = [
    ("America/Chicago", "Central Time (Iowa)"),
    ("America/New_York", "Eastern Time"),
    ("America/Denver", "Mountain Time"),
    ("America/Phoenix", "Mountain Time (Arizona, no DST)"),
    ("America/Los_Angeles", "Pacific Time"),
    ("America/Anchorage", "Alaska Time"),
    ("Pacific/Honolulu", "Hawaii Time"),
]


def to_local(dt: datetime | None, business: Business) -> datetime | None:
    """Converts a naive UTC timestamp (how everything is stored — see Call.timestamp,
    TextMessage.timestamp, Job.created_at/completed_at) to the business's configured
    timezone for display. Storage stays UTC; only rendering ever calls this."""
    if dt is None:
        return None
    tz_name = business.timezone or DEFAULT_TIMEZONE
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_TIMEZONE)
    aware_utc = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return aware_utc.astimezone(tz)
