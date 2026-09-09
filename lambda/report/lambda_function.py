"""
Report-generator endpoint.

⚠️  DELIBERATELY VULNERABLE  ⚠️
----------------------------------
VULN #5 — Command injection (RCE).

POST /api/report  takes a JSON body { "filename": "...", "title": "..." }
and shells out to `echo` to "render" a tiny report. Both fields are
interpolated into the shell command via `shell=True`, so an attacker
can submit `filename = "x; cat /etc/passwd #"` to execute arbitrary
commands on the Lambda.

Real fix: don't use `shell=True` with untrusted input. Pass arguments
as a list to subprocess.run, validate filename against a strict
whitelist (e.g. `^[a-zA-Z0-9_-]+\\.txt$`).
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))

from auth import extract_bearer, verify_token  # noqa: E402
from responses import json_response, parse_json_body  # noqa: E402


def lambda_handler(event, context):
    token = extract_bearer(event.get("headers") or {})
    if not token:
        return json_response(401, {"error": "missing bearer token"})
    try:
        verify_token(token)
    except ValueError as e:
        return json_response(401, {"error": f"invalid token: {e}"})

    body = parse_json_body(event)
    filename = body.get("filename", "report.txt")
    title = body.get("title", "Untitled")

    # ---------------------- VULN #5: command injection ----------------------
    # `shell=True` with f-string interpolation of user input. Classic
    # textbook RCE. An attacker submits `filename="r.txt; id #"` to
    # exec arbitrary commands.
    cmd = f"echo 'Report: {title}' > /tmp/{filename} && echo wrote /tmp/{filename}"
    try:
        out = subprocess.run(  # nosec B602
            cmd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return json_response(504, {"error": "report timeout"})
    # ------------------------------------------------------------------------

    return json_response(200, {
        "ok": out.returncode == 0,
        "stdout": out.stdout,
        "stderr": out.stderr,
        "cmd": cmd,
    })
