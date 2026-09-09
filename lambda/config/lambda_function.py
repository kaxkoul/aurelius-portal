"""
Config / URL-fetcher endpoint.

⚠️  DELIBERATELY VULNERABLE  ⚠️
----------------------------------
VULN #4 — Server-Side Request Forgery (SSRF).

GET /api/fetch?url=...  fetches an arbitrary URL server-side and returns
the body. There is no allow-list and no protection against internal
addresses, so an attacker can hit:
  - http://169.254.169.254/latest/meta-data/iam/security-credentials/
    (EC2/Lambda IMDS — though Lambda blocks 169.254 by default; many
    AWS services don't, and the dataflow itself is the finding)
  - http://internal.alb.example/ (private VPC services)
  - file:// (depending on the urllib version)

Real fix: validate the URL against an explicit allow-list of hostnames,
reject private/loopback IPs, and never let user input drive a server
egress request.
"""
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))

from responses import json_response  # noqa: E402


def lambda_handler(event, context):
    qs = event.get("queryStringParameters") or {}
    url = qs.get("url")
    if not url:
        return json_response(400, {"error": "url query param required"})

    # ---------------------- VULN #4: SSRF ----------------------
    # No allow-list, no scheme check, no IP validation. The user's
    # `url` is dropped straight into urlopen.
    try:
        with urlopen(url, timeout=5) as r:  # nosec B310
            body = r.read(8192).decode("utf-8", errors="replace")
            status = r.getcode()
    except URLError as e:
        return json_response(502, {"error": "fetch failed", "detail": str(e)})
    except Exception as e:  # noqa: BLE001
        return json_response(500, {"error": "fetch error", "detail": str(e)})
    # -----------------------------------------------------------

    return json_response(200, {
        "fetched_url": url,
        "status": status,
        "body_preview": body,
    })
