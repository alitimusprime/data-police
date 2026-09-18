import base64
import hashlib
import hmac
import json
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings


attempts = defaultdict(deque)


def issue_session(email):
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": email, "exp": int(time.time()) + 28800}).encode()
    ).decode()
    signature = hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def current_user(request: Request):
    token = request.cookies.get("dp_session", "")
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload))
        if data["exp"] <= time.time() or data["email"] != settings.admin_email:
            raise ValueError()
        return {"email": data["email"], "name": "Workspace administrator", "role": "admin"}
    except Exception:
        raise HTTPException(401, "Sign in to your workspace") from None


def verify_password(request, email, password):
    key = request.client.host if request.client else "local"
    recent = attempts[key]
    while recent and recent[0] < time.monotonic() - 60:
        recent.popleft()
    if len(recent) >= 10:
        raise HTTPException(429, "Too many sign-in attempts. Try again in one minute.")
    recent.append(time.monotonic())
    email_ok = hmac.compare_digest(email.encode(), settings.admin_email.encode())
    password_ok = hmac.compare_digest(
        hashlib.sha256(password.encode()).digest(), hashlib.sha256(settings.admin_password.encode()).digest()
    )
    if not (email_ok and password_ok):
        raise HTTPException(401, "Email or password is incorrect")
    recent.clear()
