"""
Job Manager — PharmaIntel BR
In-memory tracking of business jobs created by the user or by the orchestrator.
No database, no persistence across process restarts — by design (see task spec).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

VALID_PRIORITIES = ("HIGH", "MEDIUM", "LOW")
VALID_STATUSES = ("pending", "running", "blocked", "completed", "failed")

_JOBS: list[dict[str, Any]] = []
_NEXT_ID = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(
    title: str,
    request: str,
    job_type: str,
    priority: str = "MEDIUM",
    commercial_value: str | None = None,
    contract_protection_required: bool = False,
) -> dict[str, Any]:
    global _NEXT_ID

    if priority not in VALID_PRIORITIES:
        priority = "MEDIUM"

    job = {
        "job_id": _NEXT_ID,
        "title": title,
        "request": request,
        "job_type": job_type,
        "priority": priority,
        "status": "pending",
        "assigned_agents": [],
        "missing_information": [],
        "next_action": None,
        "commercial_value": commercial_value,
        "contract_protection_required": contract_protection_required,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _NEXT_ID += 1
    _JOBS.append(job)
    return job


def update_job(job_id: int, **fields: Any) -> dict[str, Any] | None:
    job = get_job(job_id)
    if not job:
        return None
    if "status" in fields and fields["status"] not in VALID_STATUSES:
        fields.pop("status")
    for key, value in fields.items():
        if key in job:
            job[key] = value
    job["updated_at"] = _now()
    return job


def get_job(job_id: int) -> dict[str, Any] | None:
    return next((j for j in _JOBS if j["job_id"] == job_id), None)


def list_jobs() -> list[dict[str, Any]]:
    return list(_JOBS)


def clear_jobs() -> None:
    """Reset in-memory state. Used by tests and to avoid unbounded growth across reruns."""
    global _NEXT_ID
    _JOBS.clear()
    _NEXT_ID = 1
