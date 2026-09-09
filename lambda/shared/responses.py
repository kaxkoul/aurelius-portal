"""Shared HTTP response helpers for vuln-demo Lambdas."""
import json


def json_response(status: int, body: dict | list, *, content_type: str = "application/json") -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": content_type,
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization,Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body) if not isinstance(body, str) else body,
    }


def html_response(status: int, body: str) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        },
        "body": body,
    }


def parse_json_body(event: dict) -> dict:
    """Return the JSON body from an API Gateway event, or empty dict."""
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        raw = base64.b64decode(raw).decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
