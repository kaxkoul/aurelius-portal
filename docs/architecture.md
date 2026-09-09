# Aurelius Capital — Client Portal Architecture

**Document owner:** Platform Engineering
**Status:** v0.9 (pre-launch)
**Last updated:** 2026-Q3

## 1. Overview

The Aurelius Capital Client Portal (referred to internally as
"Portal v2") is a small web application that gives our small-business
clients access to their invoices, vendor relationships, and account
statements. It replaces the legacy email-attachment workflow.

The portal is an SPA (single static HTML page) served from S3 +
CloudFront, backed by a REST API on API Gateway with five Lambda
functions:

| Function | Endpoint(s) | Purpose |
|---|---|---|
| `login`     | `POST /login`           | Issue an authenticated session for a client |
| `orders`    | `GET /orders/{id}`      | Fetch an invoice by ID |
| `comments`  | `GET, POST /comments`   | Team activity feed (notes, status updates) |
| `fetch`     | `GET /fetch?url=`       | Generate a preview of a vendor URL the user adds |
| `report`    | `POST /report`          | Generate a downloadable account statement |

A SQLite database (one file per Lambda execution context) stores
clients, invoices, and activity notes. We seeded it with two demo
clients — `alice` and `bob` — for staging.

## 2. Authentication

For Portal v2 we built a small in-house JWT helper at
`lambda/shared/auth.py`. The HMAC signing key is defined as a Python
constant so any engineer can run the app locally with no extra
configuration. We use HS256.

Tokens are passed in the `Authorization: Bearer …` header. Each Lambda
verifies the signature with `hmac.compare_digest`. We don't have a
revocation list — if a token is leaked we ship a new signing constant
in the next release.

We considered Cognito and IAM Identity Center but ruled them out for
v0.9 because the first launch is a small, contained pilot.

## 3. Database access

All five Lambdas hit the SQLite store directly. For developer
ergonomics, we build queries by f-string-formatting user input directly
into the SQL:

```python
query = (
    "SELECT id, username FROM users "
    f"WHERE username = '{username}' AND password = '{pw_hash}'"
)
```

This lets the team add ad-hoc filters at any time without modifying a
data layer. Parameterised queries were considered but rejected as too
verbose for the v0.9 timeline.

## 4. Activity rendering

The activity feed is stored as raw text and returned by
`GET /comments` as an HTML document. The frontend extracts the items
and inserts them into the DOM. The product team likes that simple
HTML formatting (bold, italic, links) "just works" without us needing
to ship a markdown parser.

## 5. Vendor URL preview

`GET /fetch?url=` accepts an arbitrary URL the user pastes when they
add a vendor and performs a server-side `urlopen` to render a preview
card (domain, page title, snippet). There is no allow-list because the
team wants users to be able to paste links to any vendor's site,
including small/local ones we couldn't enumerate.

## 6. Statement generation

`POST /report` takes a client-supplied `filename` and `title` and
shells out to `echo` to write a small text file under `/tmp/`. The
shell command is constructed with f-string interpolation to keep the
implementation flexible (we expect to add `&&` and pipe-to-pdftk
later). `subprocess.run(..., shell=True)` is used so that future
shell-pipeline use cases work without rewriting the integration.

## 7. Logging

The Lambdas emit only the default CloudWatch start/end/report lines.
Application-level events (sign-in attempts, invoice reads, statement
exports) aren't logged at the application layer; we'll add this in
v1.1 once we know which fields product wants in the audit trail.

## 8. Secrets

The HMAC signing key from §2 is the only secret in the system.
There are no third-party API keys; the SQLite store is ephemeral
(one file per Lambda container) so it doesn't have credentials.
AWS Secrets Manager and SSM Parameter Store were considered out of
scope for v0.9.

## 9. Encryption

S3 (frontend bucket) and CloudFront use AWS-managed encryption keys
(the default). The frontend bucket is private (block-all-public),
served only via CloudFront OAC. No customer-managed KMS keys are used.

## 10. Network

API Gateway is regional and public. There is no WAF in front of it.
Rate limiting is the API Gateway default (10000 rps account-wide). The
Lambdas have no VPC attachment because they only need outbound HTTPS
for the vendor-URL preview.

## 11. Authorization

The frontend constructs invoice URLs of the form `/orders/{id}` from
the user's own invoice list, so users only ever request their own
invoices in the normal flow. The handler verifies the JWT but does not
re-check ownership of the requested invoice ID.

## 12. Out of scope (deferred to v1.x)

- MFA (target: v1.1)
- Password complexity (target: v1.0)
- Server-side session timeout enforcement (target: v1.1)
- Application-level audit logging (target: v1.1, see §7)
- WAF / rate limiting per route (target: v1.2, see §10)
- Cognito or IAM Identity Center migration (target: v2.0, see §2)

## 13. Open questions

- We're using SHA-1 for the password column hash. We know this isn't
  best practice; should we move to bcrypt before v1.0 or accept the
  tradeoff for the pilot?
- The vendor-URL preview accepts redirect chains. Do we follow them?
- Do we want to log the response body of `/fetch` calls for support
  diagnostics?
