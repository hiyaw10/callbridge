"""POST a simulated Twilio CallStatus webhook to a locally running server.

Signature validation is skipped automatically on the server side when
TWILIO_AUTH_TOKEN is unset, which is the default local dev setup — so this
script doesn't need to compute a real Twilio signature.
"""
import argparse
import sys
import uuid
from pathlib import Path
from urllib import parse, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000/webhooks/twilio/call-status")
    parser.add_argument("--to", default="+15555550123", help="Business's Twilio number")
    parser.add_argument("--from-number", dest="from_number", default="+15555559911", help="Caller's number")
    parser.add_argument(
        "--status",
        default="no-answer",
        choices=["completed", "no-answer", "busy", "canceled", "failed"],
    )
    parser.add_argument("--sid", default=None, help="CallSid to use (random if omitted; reuse one to test idempotency)")
    args = parser.parse_args()

    call_sid = args.sid or f"CA{uuid.uuid4().hex}"
    payload = {
        "CallSid": call_sid,
        "CallStatus": args.status,
        "To": args.to,
        "From": args.from_number,
    }
    data = parse.urlencode(payload).encode()
    req = request.Request(args.url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with request.urlopen(req) as resp:
        print(f"POST {args.url} -> {resp.status}")
        print(resp.read().decode())
    print(f"CallSid used: {call_sid}")


if __name__ == "__main__":
    main()
