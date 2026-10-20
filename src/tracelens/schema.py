"""Public telemetry schema. Ground truth deliberately lives in a separate file."""
from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

METRICS = ("error_rate", "latency_ms", "cpu_pct", "memory_mb", "request_rate", "queue_depth")
ID = r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,95}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Service(StrictModel):
    name: str = Field(pattern=ID)
    metrics: dict[str, list[float]]

    @model_validator(mode="after")
    def valid_metrics(self):
        if set(self.metrics) != set(METRICS):
            raise ValueError(f"Expected exactly {METRICS}")
        lengths = {len(v) for v in self.metrics.values()}
        if len(lengths) != 1 or not 8 <= next(iter(lengths)) <= 240:
            raise ValueError("All metric series need 8..240 aligned samples")
        for key, values in self.metrics.items():
            if any(v < 0 for v in values):
                raise ValueError("Metrics must be nonnegative")
            if key == "error_rate" and any(v > 1 for v in values):
                raise ValueError("Error rates must be in [0, 1]")
            if key == "cpu_pct" and any(v > 100 for v in values):
                raise ValueError("CPU percentage must be in [0, 100]")
        return self


class Log(StrictModel):
    id: str = Field(pattern=ID)
    service: str = Field(pattern=ID)
    time: int = Field(ge=0, le=239)
    level: Literal["INFO", "WARN", "ERROR"]
    message: str = Field(min_length=1, max_length=1200)


class Span(StrictModel):
    id: str = Field(pattern=ID)
    service: str = Field(pattern=ID)
    target: str | None = Field(default=None, pattern=ID)
    time: int = Field(ge=0, le=239)
    duration_ms: float = Field(ge=0, le=3_600_000)
    status: Literal["OK", "ERROR"]
    operation: str = Field(max_length=240)
    trace_id: str = Field(max_length=128)


class Deployment(StrictModel):
    id: str = Field(pattern=ID)
    service: str = Field(pattern=ID)
    time: int = Field(ge=0, le=239)
    version: str = Field(min_length=1, max_length=100)
    summary: str = Field(max_length=500)


class Incident(StrictModel):
    id: str = Field(pattern=ID)
    title: str = Field(min_length=1, max_length=160)
    source: Literal["synthetic", "otel-lab", "imported"]
    started_at: str = Field(max_length=50)
    sample_seconds: float = Field(default=30, ge=0.000001, le=3600)
    services: list[Service] = Field(min_length=2, max_length=32)
    logs: list[Log] = Field(default_factory=list, max_length=1500)
    spans: list[Span] = Field(default_factory=list, max_length=2000)
    deployments: list[Deployment] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def references_and_ids(self):
        names = {s.name for s in self.services}
        if len(names) != len(self.services):
            raise ValueError("Duplicate service name")
        lengths = {len(s.metrics[METRICS[0]]) for s in self.services}
        if len(lengths) != 1:
            raise ValueError("Services must share a sampling grid")
        count = next(iter(lengths))
        ids = set()
        for row in [*self.logs, *self.spans, *self.deployments]:
            if row.service not in names or row.time >= count:
                raise ValueError("Unknown service or out-of-range sample index")
            if row.id in ids:
                raise ValueError("Evidence IDs must be unique within an incident")
            ids.add(row.id)
            if isinstance(row, Span) and row.target and row.target not in names:
                raise ValueError("Unknown span target")
        return self


class Label(StrictModel):
    incident_id: str = Field(pattern=ID)
    experiment_id: str = Field(pattern=ID)
    root_service: str = Field(pattern=ID)
    fault_family: str
    split: Literal["train", "validation", "test", "challenge"]


class RankedService(StrictModel):
    service: str
    probability: float = Field(ge=0, le=1)
    score: float


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=900)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class Diagnosis(StrictModel):
    status: Literal["supported", "inconclusive"]
    likely_service: str | None
    summary: str = Field(max_length=3000)
    claims: list[Claim] = Field(default_factory=list, max_length=12)
    next_steps: list[str] = Field(default_factory=list, max_length=6)
    limitations: list[str] = Field(default_factory=list, max_length=8)


def clean_identifier(value: str) -> str:
    """Normalize an imported name; callers must check for collisions."""
    cleaned = re.sub(r"[^a-zA-Z0-9_.:-]", "-", value)[:90].strip("-.")
    return cleaned or "unnamed-service"
