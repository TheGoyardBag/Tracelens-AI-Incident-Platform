# Security boundaries

This is a **single-workspace, local development prototype**, not a hardened enterprise product.

## Implemented safeguards

Bearer-token authentication for every data endpoint; constant-time token comparison; loopback default binding; restricted CORS and Host headers; JSON/body bounds; strict schemas; validated service/evidence references; generated credentials excluded from version control; parameterized SQLAlchemy queries; allowlisted read-only tools; bounded hosted calls; explicit opt-in for external telemetry; HTML-escaped telemetry; model arrays loaded without pickle; no automatic remediation.

## Do not assume

There is no enterprise identity provider, per-user authorization, tenant isolation, encrypted-at-rest database policy, secret vault, tamper-resistant audit storage, distributed rate limiter, or independent security review. A shared bearer token represents the entire local workspace. Session storage is not safe against every XSS threat.

Regex redaction misses secrets and personal information. Never send sensitive telemetry to a hosted model merely because it was run through a regex. Logs may contain prompt injection; structured tools and reference validation reduce the reachable actions but do not prove that the model will always follow instructions or produce a correct answer.

LLM outputs are treated as untrusted text. Citation validation checks that the IDs exist and concern a known service, not that each natural-language claim logically follows from those sources. No external action is executed from model output.

Human-review records do not authorize an external operation. The API has no write credentials to infrastructure and no endpoints that perform remediation.

## Running safely

Keep the API on 127.0.0.1. Do not put real logs into public GitHub, screenshots, tests, or artifacts. Do not bind to the public internet without adding HTTPS, real authentication/authorization, an ingress size/rate limit, proper key management and a security review. Run only one API worker with the included in-process scheduler.

The Next.js proxy buffers POST bodies before forwarding. Put an ingress body limit in front of it for any non-local deployment. The backend independently enforces its own 2 MB bound.

Only load model artifacts you trust. The manifest checksum detects accidental modifications, not a malicious publisher who can replace both the weights and manifest.

## Reporting issues

For a local fork, contact its maintainer privately for vulnerabilities. Do not publish real credentials or sensitive example telemetry in an issue. Rotate any credential exposed in logs or version history.
