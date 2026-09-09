"""
Login endpoint.

⚠️  DELIBERATELY VULNERABLE  ⚠️
----------------------------------
VULN #1 — SQL injection.

The username is concatenated directly into a raw SQL string. An attacker
can submit `' OR '1'='1` (or similar) as the username to bypass auth.

Real fix: use parameterised queries (the sqlite3 driver supports `?`
placeholders) and never concatenate user input into SQL.

This file is part of the AWS Security Agent demo. Do not reuse.
"""
import hashlib
import sys
from pathlib import Path

# Make the `shared/` package importable inside the Lambda zip.
sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))

from auth import issue_token  # noqa: E402
from db import get_db  # noqa: E402
from responses import json_response, parse_json_body  # noqa: E402


def lambda_handler(event, context):
    body = parse_json_body(event)
    username = body.get("username", "")
    password = body.get("password", "")

    if not username or not password:
        return json_response(400, {"error": "username and password required"})

    pw_hash = hashlib.sha1(password.encode()).hexdigest()
    db = get_db()

    # ---------------------- VULN #1: SQL injection ----------------------
    # The `username` is dropped straight into the SQL string. Submitting
    # `' OR '1'='1' --` returns the first user; an attacker can also use
    # UNION SELECT to dump arbitrary tables.
    query = (
        "SELECT id, username FROM users "
        f"WHERE username = '{username}' AND password = '{pw_hash}'"
    )
    # --------------------------------------------------------------------

    try:
        cur = db.execute(query)
    except Exception as e:  # noqa: BLE001
        # We deliberately leak the SQL error to the client — also a finding.
        return json_response(500, {"error": "db error", "detail": str(e), "query": query})

    row = cur.fetchone()
    if not row:
        return json_response(401, {"error": "invalid credentials"})

    token = issue_token(user_id=row["id"], username=row["username"])
    return json_response(200, {
        "token": token,
        "user": {"id": row["id"], "username": row["username"]},
    })
