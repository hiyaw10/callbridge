from app.models import Business

DEFAULT_MISSED_CALL_MESSAGE = "Sorry we missed you — this is {business_name}, how can we help?"
DEFAULT_REVIEW_REQUEST_MESSAGE = "Thanks for choosing {business_name}! Mind leaving us a quick Google review? [link]"


def render_missed_call_message(business: Business) -> str:
    template = business.missed_call_message or DEFAULT_MISSED_CALL_MESSAGE
    return template.replace("{business_name}", business.name)


def render_review_request_message(business: Business) -> str:
    template = business.review_request_message or DEFAULT_REVIEW_REQUEST_MESSAGE
    return template.replace("{business_name}", business.name)
