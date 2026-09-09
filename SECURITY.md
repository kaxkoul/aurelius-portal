# Security disclosure

**This repository is intentionally vulnerable.**

It exists to give AWS Security Agent demos something concrete to find.
Every Lambda function under `lambda/` and the architecture document at
`docs/architecture.md` contain deliberate security flaws. The flaws are
not bugs — they are the product.

## Do not

- Do **not** copy code from this repo into a real application
- Do **not** deploy it under your real customer-facing domain
- Do **not** point a public URL at it long-term
- Do **not** report the deliberate vulnerabilities as a security issue

## What to do instead

If you're running a demo against this app, **tear it down when you're
done**:

```bash
./scripts/teardown.sh
```

If you found a *non-deliberate* vulnerability (e.g. a Lambda that
unintentionally exposes the deploy account, or the CDK stack creates a
publicly-writable bucket), please open a private GitHub security
advisory.

## Catalogue of intentional vulnerabilities

| # | Vuln | File |
|---|---|---|
| 1 | SQL injection | `lambda/login/lambda_function.py` |
| 2 | Insecure Direct Object Reference (IDOR) | `lambda/orders/lambda_function.py` |
| 3 | Stored Cross-Site Scripting (XSS) | `lambda/comment/lambda_function.py` |
| 4 | Server-Side Request Forgery (SSRF) | `lambda/config/lambda_function.py` |
| 5 | Command injection (RCE) | `lambda/report/lambda_function.py` |
| 6 | Hardcoded JWT signing secret | `lambda/shared/auth.py` |
| – | Plain SHA-1 password hashing | `lambda/shared/db.py` |
| – | SQL error leak in response body | `lambda/login/lambda_function.py` |
| – | Multiple design-level violations | `docs/architecture.md` |

## License

Proprietary / private. Do not redistribute.
