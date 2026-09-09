# Organizational Security Requirements

> Paste this content into the AWS Security Agent **Organizational
> Security Requirements** field for the `vuln-demo` Agent Space.
> The agent uses these rules to ground both **Design Security Review**
> and **Code Security Review** findings.

These rules are deliberately written so that both `docs/architecture.md`
and the code under `lambda/` violate at least one each — giving the
Agent something concrete to flag.

---

## R1. Authentication

- All authentication MUST use **AWS Cognito** or **IAM Identity Center**.
- Custom JWT implementations are **not allowed**.
- If JWTs are unavoidable for an external integration, the signing
  secret MUST come from **AWS Secrets Manager** at runtime — never
  hard-coded, never in environment variables, never in source.

## R2. Database access

- All SQL MUST use **parameterised queries** (e.g. `?` placeholders in
  `sqlite3`, `%s` in `psycopg2`, named params in SQLAlchemy).
- String concatenation or f-string interpolation of user input into SQL
  is **forbidden** in any code path that reaches a database driver.

## R3. Output encoding

- Any user-supplied content rendered in HTML MUST be HTML-escaped on
  output, OR returned as JSON and rendered via `textContent` /
  React `{value}` (never `innerHTML` / `dangerouslySetInnerHTML`).

## R4. Server-side egress

- Endpoints that fetch external URLs MUST validate the URL against an
  **explicit allow-list** of hostnames.
- Loopback (`127.0.0.0/8`), link-local (`169.254.0.0/16`), and private
  RFC1918 ranges MUST be blocked.
- Only `https://` is permitted; `file://`, `gopher://`, `dict://`, etc.
  are forbidden.

## R5. Shell execution

- `subprocess` calls with `shell=True` are **forbidden** when any
  argument can be influenced by user input.
- Prefer `subprocess.run([...], shell=False)` with the argument list
  form. Validate filenames / paths against a strict allow-list regex.

## R6. Secrets management

- All secrets — API keys, signing secrets, DB passwords, third-party
  tokens — MUST be stored in **AWS Secrets Manager** or **SSM
  Parameter Store** (SecureString) and fetched at runtime.
- Hard-coded secrets in source, configuration files, or environment
  variables in IaC are not allowed.

## R7. Encryption

- Customer data at rest MUST be encrypted with **customer-managed KMS
  keys** (not AWS-managed default keys).
- Applies to S3 buckets containing user-generated content, RDS
  databases, and Secrets Manager secrets that store customer data.

## R8. Audit logging

- Every authentication attempt (success and failure), every order
  read, every comment write, and every report generation MUST emit a
  structured CloudWatch Logs entry containing:
  - `eventName` (e.g. `auth.login`, `order.read`)
  - `userId` (or `anonymous`)
  - `requestId`
  - `outcome` (`success` / `failure`)
  - `timestamp` (ISO 8601 UTC)

## R9. Network protection

- Public REST APIs MUST sit behind **AWS WAF v2** with at least:
  - Managed rule group `AWSManagedRulesCommonRuleSet`
  - A rate-based rule (e.g. 1000 requests / 5 min / IP)
- API Gateway throttling MUST be enabled with sensible defaults
  (≤ 100 requests/sec per route by default).

## R10. Authorization

- For every resource fetch, the handler MUST verify the calling
  principal has access to the **specific resource ID** before
  returning it. Authentication alone is not authorization.
- Examples: `GET /orders/{id}` MUST check `order.user_id ==
  caller.user_id` (or that the caller has an admin role).

---

## How violations should be reported

When the agent finds a violation, the finding should reference:

- The specific requirement number above (e.g. **R2**, **R6**)
- The file and line
- A concrete remediation snippet

Findings that don't match any of the rules above are still valuable but
should be marked as "general best practice" rather than "organizational
requirement violation".
