"""Simple in-memory rate limiting for auth endpoints."""

import time
from collections import defaultdict

from flask import request

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 300

_attempts = defaultdict(list)


def _client_key():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def auth_rate_limited():
    key = _client_key()
    now = time.time()
    recent = [t for t in _attempts[key] if now - t < WINDOW_SECONDS]
    _attempts[key] = recent
    if len(recent) >= MAX_ATTEMPTS:
        return True
    recent.append(now)
    _attempts[key] = recent
    return False
