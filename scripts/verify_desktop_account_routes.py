"""Verify desktop Flask account routes for web-first auth flow."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(ROOT, "client_app")
sys.path.insert(0, CLIENT)
os.chdir(CLIENT)
os.environ.setdefault("FROGSWORK_ACCOUNT_API_URL", "http://127.0.0.1:8787")

from app import app  # noqa: E402

client = app.test_client()

# Clear any persisted auth from prior runs so /account/login hits the web redirect.
from account import auth_store  # noqa: E402

auth_store.clear_auth()

checks = []


def check(path, expect_text=None, status=200):
    resp = client.get(path, follow_redirects=False)
    ok = resp.status_code == status
    body = resp.get_data(as_text=True)
    if expect_text and expect_text not in body:
        ok = False
    checks.append((path, ok, resp.status_code, expect_text or ""))


check("/account/login", "Continue in your browser")
check("/account/subscribe", "Continue in your browser")
check("/account/password", "Continue in your browser")
check("/account/stripe/return", "Continue in your browser")

resp = client.get(
    "/account/auth/callback?access_token=test_token&refresh_token=ref&email=dev@test.com",
    follow_redirects=False,
)
checks.append(
    (
        "/account/auth/callback",
        resp.status_code in (302, 303),
        resp.status_code,
        "redirect home",
    )
)

failed = [c for c in checks if not c[1]]
for path, ok, code, detail in checks:
    print(f"{'PASS' if ok else 'FAIL'} {path} -> {code} {detail}")

sys.exit(1 if failed else 0)
