# Development guidance

Keep the default demo runnable without paid APIs. Never introduce production telemetry or API keys into tracked files. Do not add fabricated benchmark claims. Training labels must stay outside serving and agent inputs. Default investigation is read-only; human review is an audit record, not remediation authorization.

Run `pytest`, `node --test tests/frontend.test.mjs`, and the frontend type/build checks when their dependencies are installed. Changes to model features require retraining and a feature-schema version review. Preserve experiment-group splits and evaluate on untouched held-out data. Do not select an architecture by its test-set score.

The API intentionally runs as one process. Do not add Uvicorn workers without replacing the in-process job queue and startup interruption policy. Treat imported records, provider responses and log text as untrusted data. Read reports/VALIDATION.md before assuming an optional integration was tested.
