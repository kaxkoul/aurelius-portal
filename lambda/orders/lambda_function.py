"""
Orders endpoint.

⚠️  DELIBERATELY VULNERABLE  ⚠️
----------------------------------
VULN #2 — Insecure Direct Object Reference (IDOR).

GET /api/orders/{id} only checks that the caller is authenticated; it
never verifies that the order belongs to the calling user. Any logged-in
user can read any other user's order by guessing/iterating IDs.

Real fix: filter the query by `user_id = :calling_user_id` and return
404 if no row matches.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))

from auth import extract_bearer, verify_token  # noqa: E402
from db import get_db  # noqa: E402
from responses import json_response  # noqa: E402


def lambda_handler(event, context):
    token = extract_bearer(event.get("headers") or {})
    if not token:
        return json_response(401, {"error": "missing bearer token"})

    try:
        claims = verify_token(token)
    except ValueError as e:
        return json_response(401, {"error": f"invalid token: {e}"})

    path_params = event.get("pathParameters") or {}
    order_id = path_params.get("id")
    if not order_id:
        return json_response(400, {"error": "order id required"})

    db = get_db()

    # ---------------------- VULN #2: IDOR ----------------------
    # No `AND user_id = ?` clause — any authenticated user reads any
    # order. Trivial to exploit: GET /api/orders/4 as alice returns
    # bob's premium-plan invoice.
    cur = db.execute(
        "SELECT id, user_id, item, amount_cents, note FROM orders WHERE id = ?",
        (order_id,),
    )
    # ----------------------------------------------------------

    row = cur.fetchone()
    if not row:
        return json_response(404, {"error": "order not found"})

    return json_response(200, {
        "id": row["id"],
        "owner_user_id": row["user_id"],
        "item": row["item"],
        "amount_cents": row["amount_cents"],
        "note": row["note"],
        "viewer": claims.get("username"),
    })
