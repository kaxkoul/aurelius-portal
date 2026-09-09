# Aurelius Capital — Client Portal (AWS Security Agent demo target)

> ⚠️ **THIS REPOSITORY IS DELIBERATELY VULNERABLE.** It is staged to
> look like a real client portal so a demo audience cannot tell where
> the bugs are by looking at the UI — only the AWS Security Agent
> can. Do **not** deploy this publicly under your real domain, do
> **not** copy code from it into anything real, and tear down the
> deployed stack as soon as your demo is done.

A fictional small-business invoicing portal — "Aurelius Capital" —
used to demo the three core capabilities of [AWS Security Agent](https://docs.aws.amazon.com/securityagent/latest/userguide/what-is.html):

| Capability | What this repo gives the agent |
|---|---|
| **Design security review** | `docs/architecture.md` — an internal architecture doc that violates the org ruleset |
| **Code security review** | `lambda/` — Python source with 6 deliberate vulnerabilities |
| **Penetration testing** | A deployed CloudFront URL the agent can attack |

The org ruleset that all three capabilities are evaluated against is
in [`org-security-requirements.md`](./org-security-requirements.md).

## The demo narrative

The portal is presented to your audience as a **legit-looking SaaS
product**: branded login, invoice list, vendor link previews,
activity feed, statement export. None of the vulns are visible in
the UI — there's nothing labelled "SQL injection here". The audience
sees a normal small-business app.

The Security Agent then:

1. **Reads the architecture doc** and flags six insecure design
   choices the audience never noticed (Design Review).
2. **Scans the Lambda code** and surfaces the same problems plus a
   hardcoded JWT signing secret, parameter-less SQL, etc.
3. **Pen-tests the live URL** and demonstrates each vuln being
   exploited end-to-end with a reproducible attack path.

## What's in here

```
.
├── infrastructure/cdk/         Python CDK stack
├── lambda/                     5 vulnerable Lambda handlers + shared/
│   ├── login/                  → SQL injection
│   ├── orders/                 → IDOR
│   ├── comment/                → Stored XSS
│   ├── config/                 → SSRF
│   ├── report/                 → Command injection
│   └── shared/                 auth.py (hardcoded JWT secret), db.py
├── frontend/index.html         Polished Aurelius portal UI
├── docs/architecture.md        Internal architecture doc with violations
├── org-security-requirements.md
├── scripts/{deploy,teardown}.sh
└── SECURITY.md                 Disclosure of intentional vulns
```

## Vulnerability cheat-sheet (don't show this to the audience)

| # | Vuln | Where it lives in the UI | File |
|---|---|---|---|
| 1 | SQL injection | Sign-in form | `lambda/login/lambda_function.py` |
| 2 | IDOR | Invoice detail page (`/orders/{id}`) | `lambda/orders/lambda_function.py` |
| 3 | Stored XSS | Team activity feed | `lambda/comment/lambda_function.py` |
| 4 | SSRF | Vendor link preview | `lambda/config/lambda_function.py` |
| 5 | Command injection | Statement export | `lambda/report/lambda_function.py` |
| 6 | Hardcoded JWT secret | (not visible — code-only) | `lambda/shared/auth.py` |

## Prerequisites

- AWS CLI v2 configured with credentials for the demo account
- Python 3.11+ and `python3 -m venv`
- AWS CDK v2 (`npm install -g aws-cdk`)
- The target region must be **CDK-bootstrapped**:
  ```bash
  cdk bootstrap aws://<account>/<region>
  ```

## Deploy

```bash
./scripts/deploy.sh
```

This will:
1. Build Lambda assets locally under `.build/` (no Docker required)
2. Create a Python venv and install CDK deps
3. `cdk deploy` the `vuln-demo` stack
4. Inject the API Gateway URL into the frontend HTML and re-upload

When done you'll see something like:

```
Frontend URL:  https://dXXXXXXXXXX.cloudfront.net
API base URL:  https://YYYYYYYYYY.execute-api.<region>.amazonaws.com/prod
Test users:    alice / alice-pass-123
               bob   / bob-pass-456
```

## Tear down

```bash
./scripts/teardown.sh
```

Runs `cdk destroy` and cleans up local build artifacts. The S3 bucket
is created with `auto_delete_objects=True`, so no manual emptying.

## Demo runbook (~15 min)

Before you start, configure an Agent Space against this app — see
[Agent Space setup](#agent-space-setup) below. Don't tell your
audience this is a vulnerable app. Open the portal, click around,
let it look normal.

### Act 1 — Design Security Review (3 min)

> Frame: "The architecture team submitted this design doc for security
> review."

1. Open the AWS Security Agent web app, pick the agent space
2. **Design Security Review** → upload `docs/architecture.md`
3. Wait for analysis (~1–2 min)
4. Findings should reference the org-requirement IDs (R1, R2, R3, …)
5. Audience reaction — "I read that doc and didn't catch any of these."

### Act 2 — Code Security Review (5 min)

**2a. Full-repo scan**
1. **Code Security Review** → **Create code review**, source = the
   connected GitHub repo
2. Wait ~3–5 min
3. The agent flags SQLi (R2), SSRF (R4), command injection (R5), and
   the hardcoded JWT secret (R1/R6)
4. On any finding, click **Generate fix** → the agent opens a
   remediation PR

**2b. Pull-request comments**
1. Push a small new vuln on a branch and open a PR
2. Within minutes the agent posts review comments

### Act 3 — Penetration Testing (5 min)

> Frame: "Now let's see if any of those code findings are reachable
> in production."

1. **Penetration Testing** → **Create pentest**
2. Target URL = the deployed CloudFront URL
3. Auth: `alice / alice-pass-123`
4. Source repo: same connected repo (gives the agent context)
5. Click **Start**
6. Findings appear with reproducible attack paths:
   - SQLi via `' OR '1'='1' --` in the sign-in form
   - IDOR by reading invoice ID 4 as alice (it's bob's premium plan)
   - Stored XSS via a `<script>` tag in an activity note
   - SSRF via vendor URL like `http://169.254.169.254/...`
   - Command injection via filename `r.txt; id #` on the statement
     export

### Wrap (2 min)

- Each finding maps back to an org-requirement ID
- The same agent space drove design + code + runtime
- Tear-down is a single script — show that

## Agent Space setup

The Agent Space is configured **manually in the AWS Console** (no
CFN/CDK construct yet):

1. Go to [AWS Security Agent console](https://us-west-2.console.aws.amazon.com/securityagent/agents)
2. Either create a new Agent Space or reuse an existing one
3. **Organizational Security Requirements**: paste contents of
   `org-security-requirements.md`
4. **GitHub integration**: authorize the AWS Security Agent GitHub
   App on the connected repository
5. **Target domain**: enter the CloudFront URL from `deploy.sh` and
   click **Verify**

## Cost

While deployed: ~**$0.10/day** — CloudFront + tiny S3 + per-request
Lambda. There's no RDS or NAT.

Security Agent reviews + pentests are billed separately.

## See also

- [`SECURITY.md`](./SECURITY.md) — disclosure of intentional vulns
- [`docs/architecture.md`](./docs/architecture.md) — internal arch doc
- [`org-security-requirements.md`](./org-security-requirements.md) — the ruleset
