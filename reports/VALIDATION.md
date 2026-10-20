# Validation record

This records what was actually executed while creating the repository. It is not a claim that the GitHub Actions workflow has run in your account, that an AWS service was deployed, or that the Next.js application was built.

## Executed and passed

| Check | Actual result |
|---|---|
| Editable Python package installation | `pip install --no-deps --no-build-isolation -e .` succeeded using the available environment. This does not validate a clean dependency download. |
| Python tests | **77 passed**; schema validation, ML training/inference, grouped partitions, tool boundaries, mocked hosted-model behavior, persistence, authenticated APIs, SSE replay, feedback, review records, and OTLP conversion. |
| Python coverage | **946 / 1,114 executable statements covered (84.9%)** for the configured `tracelens` package. Coverage is a test-coverage measure, not a reliability guarantee. |
| JavaScript unit tests | **8 passed**; HTML escaping, SSE parsing, incomplete frames, chart safety and formatting. |
| UI interactions | **10 checks passed**, no uncaught JavaScript errors, mobile width 390 px without horizontal overflow. See the browser-method limitation below. |
| Shared TypeScript API utilities | `web/lib/api.ts` and `web/lib/types.ts` passed strict standalone TypeScript checking. |
| All TypeScript/TSX source syntax | **7 files**, no syntax-transpilation errors. This is **not** full React/Next type checking. |
| Model training | Full GRU ranker, separately retrained no-log/no-graph ablations, gradient boosting and a heuristic were evaluated. Training reports and the trained full-model artifact are included. |
| Artifact/data integrity | Weights hash, dataset hash, feature schema, experiment grouping and held-out demo exports verified. |
| Actual OpenTelemetry instrumentation | The local workload generated **64 SDK spans**; JSON conversion and model-backed CLI investigation succeeded. The result is explicitly **inconclusive/uncalibrated** for imported telemetry. |
| Python compilation | Source, scripts, examples and tests passed `compileall`. |

Python test output, coverage and browser details are in `pytest.xml`, `coverage.json`, `browser-smoke.json`, `frontend-syntax.json` and `environment.json`. Model results are in `evaluation.json` and `EVALUATION.md`.

### Browser method and screenshots

The screenshots are rendered from the actual bundled **no-Node dashboard**, not design mockups and not the separate Next.js frontend. This environment restricts browser navigation. Playwright therefore mounted the real application HTML/CSS/JavaScript in an in-memory Chromium page; a Python HTTP bridge sent its requests to a real running FastAPI server and persistent development database. The bridge buffers SSE responses.

That test validates actual login, ranking/result rendering, citation inspection, feedback, review, activity, evaluations, audit history, mobile layout and escaped imported text. It does **not** establish direct-browser network behavior, incremental browser streaming, cross-origin behavior, or a Next.js production build. The Python API tests separately exercise the SSE endpoint and replay behavior.

The reusable `scripts/browser_smoke.py` supports ordinary direct navigation on your own machine; run it against an expendable local development database because it creates feedback, review and test-incident records. `--bridge` reproduces the restricted-environment harness.

## Implemented but not executed here

- A complete `npm install`, Next.js/React type check, production build and Next.js browser session. Container DNS access to the npm registry was unavailable. No npm lockfile is fabricated.
- Docker/Compose builds and container health checks. Docker is not available here.
- PostgreSQL-backed operation. The SQLAlchemy implementation and optional deployment configuration are supplied, but validation used SQLite.
- A live Anthropic API call. Provider behavior was tested with mocked HTTP responses, including tool selection, failure, token accounting and unsupported citations. No API key is bundled and no paid call was made.
- Optional LangGraph and MLflow integrations. Their adapters are supplied but these extra dependencies were not installed here.
- A real RCAEval benchmark, customer outage data, AWS deployment, or distributed microservice workload. The bundled benchmark is generated; the SDK demonstration is one process with logical services.
- Any destructive or operational remediation. Human review is a persisted audit record only; the application contains no cloud-change tools.

## Reproduce locally

```bash
python -m pip install -e ".[dev,otel]"
python -m pytest -q --cov=tracelens --cov-report=json:reports/coverage.json --junitxml=reports/pytest.xml
node --test tests/frontend.test.mjs
python scripts/check_artifacts.py
python examples/otel_lab.py --out examples/lab-traces.json
python scripts/import_otlp.py examples/lab-traces.json --id otel-lab --out examples/lab-incident.json
python -m tracelens.cli rank examples/lab-incident.json
cd web
npm install
npm run typecheck
npm run build
```

For the browser check, install `.[browser]`, run `python -m playwright install chromium`, start the API, and run `python scripts/browser_smoke.py` from another terminal. It uses your local `.env` token.

Run the optional integrations yourself before describing them as validated. Repeat model experiments on more seeds and independent real data before drawing real-world performance conclusions.
