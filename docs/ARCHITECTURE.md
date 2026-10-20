# Architecture and decisions

## 1. Keep the application separate from experimental truth

Training reads public incident records and a separate label file. Serving reads only model artifacts and a small label-free demo export. The schema rejects unexpected fields. This keeps the agent from “solving” a case by reading `root_service` or a fault-injection flag. Features never include titles, IDs, experiment IDs or split assignments.

Any API upload is marked `imported`, regardless of a client-provided `source`. A user cannot turn real telemetry into a calibrated synthetic case merely by changing its source string. This is a safety policy, not a provenance signature.

## 2. Rank services, then investigate

The same small neural scoring network processes every service, combining temporal changes, textual log features and dependency statistics. This avoids binding the output head to six hard-coded service IDs. A candidate probability is always relative to the provided set of services.

The default workflow reads metrics/logs/traces for the top two services, deployment records for the top service, and reference runbooks. The evidence registry assigns namespaced IDs. A diagnosis cannot cite an ID that was not retrieved in that run. Runbooks alone cannot support a “supported” incident diagnosis.

The hosted workflow exposes the same read-only tools with explicit JSON schemas. The provider chooses its tool sequence. A separate finishing tool returns a typed diagnosis. Unknown services, unobserved evidence IDs, malformed arguments and unsupported actions are rejected. On a provider error or invalid result, the application emits a warning and switches to a visibly labeled deterministic fallback.

## 3. Deliberately bounded side effects

There is no remote shell, unrestricted fetch, Kubernetes action, AWS write permission, or code execution tool. “Record human review” writes an audit record only. It does not roll back, restart, isolate or delete anything. Feedback is recorded for future manual curation and is never immediately treated as a training label.

## 4. Job lifecycle and persistence

`queued -> running -> complete | failed`. Startup marks leftover queued/running jobs `interrupted`. Users may start another investigation. The system does not claim to resume an LLM midway through a tool call.

A two-worker thread pool and eight-slot semaphore bound concurrent work. SQLAlchemy stores incidents, runs, event records, feedback, human-review records and audit entries. SQLite uses WAL and a busy timeout; a PostgreSQL URL is supported by the same tables but was not integration-tested here.

SSE clients can replay from a persisted event ID. Reconnects do not repeat already consumed events. Idempotency keys prevent duplicate submissions from creating multiple runs; a key cannot be reused for a different request. This is one application process, not a distributed job scheduler. Run a single Uvicorn worker. Before scaling horizontally, introduce an external queue, job leases, ownership and cancellation semantics.

## 5. User interfaces

`web/` contains the React/Next.js implementation. An allowlisted server route proxies API requests and streaming responses without embedding the local token in the frontend build. `API_ORIGIN` is server configuration, not a caller-controlled URL.

`src/tracelens/static/` is an independent, no-Node implementation of the same workspace for quick local use. Both talk to the same backend. React escapes text by default; the plain-JavaScript dashboard explicitly escapes all telemetry. There are no injected remote fonts or chart libraries.

## 6. Honest uncertainty

The interface says “leading hypothesis,” not “proven cause.” Its evidence statements describe measured changes and failed spans. The inference layer abstains on imported data, weak signal, sparse evidence, or low candidate scores. Imported scores may still be shown to support exploration, but are not presented as trusted probabilities.

Reference integrity is tested, semantic entailment is not automatically established, and causality is not established. Do not confuse a successful schema check with a correct explanation.

## Tradeoffs and deliberate exclusions

- A trained 6k-parameter model is easier to reproduce on a laptop than a foundation-model fine-tune.
- Hashed text features avoid a mandatory model download, but do not provide pretrained semantic language understanding.
- SQLite and an in-process queue keep the demo small; they are not a multi-region architecture.
- The no-Node interface makes the core usable even where npm access is unavailable; it does not prove the separate Next.js production bundle has built.
- Optional LangGraph and MLflow adapters are present, not runtime requirements.
- There is no automatic RCAEval downloader, live streaming collector, enterprise SSO, multi-tenancy, cloud deployment, or automatic remediation in this version.
