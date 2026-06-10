"""Shared dev-helper: log in via /auth/login and return access token + headers.

Reads ADMIN_EMAIL + ADMIN_PASSWORD from env. Scripts that hit protected endpoints
use this to obtain a short-lived JWT instead of relying on the removed
``settings.auth_token`` legacy field.
"""

import os
import sys

import httpx


def login(api_base: str = "http://localhost:8000") -> dict[str, str]:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if not email or not password:
        sys.exit("ADMIN_EMAIL and ADMIN_PASSWORD env vars are required")

    resp = httpx.post(
        f"{api_base}/auth/login",
        json={"email": email, "password": password},
        timeout=10.0,
    )
    if resp.status_code != 200:
        sys.exit(f"Login failed ({resp.status_code}): {resp.text}")
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
