"""
Shared authentication helpers.

⚠️  DELIBERATELY VULNERABLE — this file is part of a demo for AWS Security
    Agent code review. Do not use any of this in production.

The JWT secret below is hardcoded on purpose so that AWS Security Agent's
code review can flag it as a "secrets in source" finding.
"""
import base64
import hashlib
import hmac
import json
import time

# VULN #6 (code-review only): hardcoded JWT signing secret.
# Real apps must read this from AWS Secrets Manager or SSM Parameter Store.
JWT_SECRET = "demo-jwt-secret-please-rotate-before-prod"  # nosec B105
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 3600


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(user_id: int, username: str) -> str:
    header = {"alg": JWT_ALG, "typ": "JWT"}
    payload = {
        "sub": user_id,
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_TTL_SECONDS,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def verify_token(token: str) -> dict:
    """Verify a JWT and return its payload, or raise ValueError."""
    try:
        h, p, s = token.split(".")
    except ValueError as e:
        raise ValueError("malformed token") from e

    expected = _b64url(
        hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, s):
        raise ValueError("bad signature")

    payload = json.loads(_b64url_decode(p))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("expired")
    return payload


def extract_bearer(headers: dict) -> str | None:
    """Pull a bearer token out of the Authorization header (case-insensitive)."""
    for k, v in (headers or {}).items():
        if k.lower() == "authorization":
            parts = v.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1]
    return None
