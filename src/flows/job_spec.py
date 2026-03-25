from __future__ import annotations

# Re-export domain models and adapter functions for backward compatibility
from flows.adapters.inbound.schema import parse_job_spec_json
from flows.domain.job_spec import JobSpec, JobSpecError

__all__ = ["JobSpec", "JobSpecError", "parse_job_spec_json"]
