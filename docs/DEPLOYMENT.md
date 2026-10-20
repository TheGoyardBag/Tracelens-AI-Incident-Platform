# Local deployment and operational boundaries

## Python

Run the setup from the repository root. The API finds the repository's `.env`, artifacts and demo export automatically. `TRACELENS_ROOT` can override the root. State is kept in `.tracelens/app.db` unless `DATABASE_URL` is set. Model weights are read-only; API feedback never changes them.

Use **one Uvicorn worker**. The included queue is in-process and is not appropriate for horizontal replicas sharing a database. On a restart, unfinished jobs are marked interrupted. Already completed results, feedback and evidence remain available.

## Docker

`docker compose up --build` runs the API and no-Node dashboard. `docker compose --profile web up --build` additionally builds the React/Next.js frontend. Builds need network access for dependencies. The CPU PyTorch package is still a significant download. These recipes were not executed in the build environment because Docker is not available there.

A named volume persists SQLite state. `docker compose down` keeps it. `docker compose down -v` deletes it; do not use that command when you need to retain your investigations.

## PostgreSQL override

Set a randomly generated, URL-safe `POSTGRES_PASSWORD` in the untracked root `.env`. Then run:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml --profile web up --build
```

This creates a separate PostgreSQL store and does not migrate an existing SQLite database. The schema is created by SQLAlchemy at startup for this prototype; introduce explicit schema migrations before evolving a persistent shared deployment. Do not use this configuration for customer data without backup, key management, access controls and a security review.

PostgreSQL code paths are provided but were not integration-tested during creation. Verify startup, idempotent submissions, feedback and concurrent job behavior before relying on them.

## What would be required for AWS/ECS

Build and scan images; push to your own registry; provide a real identity layer and external secrets; use a private database; configure TLS ingress and egress restrictions; replace the thread-pool queue with durable jobs; add job leases and per-workspace authorization; define telemetry retention and deletion; perform adversarial and load testing. No Terraform, AWS account provisioning or live AWS deployment is part of this repository.

Do not add “deployed to AWS” to the project description until you actually deploy and validate it.
