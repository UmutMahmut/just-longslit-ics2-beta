from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from justls.ics.kernel.errors import ErrorCode, ErrorInfo, ICSException
from justls.ics.kernel.states import CommandSource


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(slots=True)
class CommandRequest:
    command_id: str
    subsystem: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    source: CommandSource = CommandSource.INTERNAL
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        subsystem: str,
        action: str,
        *,
        params: dict[str, Any] | None = None,
        source: CommandSource = CommandSource.INTERNAL,
        command_id: str | None = None,
    ) -> "CommandRequest":
        return cls(
            command_id=command_id or f"cmd-{uuid4().hex[:12]}",
            subsystem=subsystem,
            action=action,
            params=params or {},
            source=source,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "subsystem": self.subsystem,
            "action": self.action,
            "params": self.params,
            "source": self.source.value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class JobRecord:
    job_id: str
    request: CommandRequest
    status: JobStatus = JobStatus.ACCEPTED
    accepted_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    state_before: str | None = None
    state_after: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: ErrorInfo | None = None

    @classmethod
    def create(
        cls,
        request: CommandRequest,
        *,
        job_id: str | None = None,
        state_before: str | None = None,
    ) -> "JobRecord":
        return cls(
            job_id=job_id or f"job-{uuid4().hex[:12]}",
            request=request,
            state_before=state_before,
        )

    def mark_running(self) -> None:
        self.status = JobStatus.RUNNING
        self.started_at = utc_now()

    def mark_succeeded(
        self,
        *,
        result: dict[str, Any] | None = None,
        state_after: str | None = None,
    ) -> None:
        if self.started_at is None:
            self.started_at = utc_now()
        self.status = JobStatus.SUCCEEDED
        self.finished_at = utc_now()
        self.result = result or {}
        self.state_after = state_after
        self.error = None

    def mark_failed(
        self,
        error: ErrorInfo,
        *,
        state_after: str | None = None,
    ) -> None:
        if self.started_at is None:
            self.started_at = utc_now()
        self.status = JobStatus.FAILED
        self.finished_at = utc_now()
        self.error = error
        self.state_after = state_after

    def mark_aborted(
        self,
        *,
        reason: str = "Job aborted.",
        state_after: str | None = None,
    ) -> None:
        if self.started_at is None:
            self.started_at = utc_now()
        self.status = JobStatus.ABORTED
        self.finished_at = utc_now()
        self.error = ErrorInfo(
            code=ErrorCode.UNKNOWN,
            message=reason,
            retriable=True,
        )
        self.state_after = state_after

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "accepted_at": self.accepted_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "request": self.request.to_dict(),
            "result": self.result,
            "error": self.error.to_dict() if self.error else None,
        }


class JobTracker:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._order: list[str] = []

    def create_job(
        self,
        request: CommandRequest,
        *,
        state_before: str | None = None,
    ) -> JobRecord:
        job = JobRecord.create(request, state_before=state_before)
        self._jobs[job.job_id] = job
        self._order.append(job.job_id)
        return job

    def get_job(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def latest_job(self) -> JobRecord | None:
        if not self._order:
            return None
        return self._jobs[self._order[-1]]

    def list_jobs(self, *, limit: int = 20) -> list[JobRecord]:
        ids = self._order[-limit:]
        return [self._jobs[job_id] for job_id in reversed(ids)]

    def mark_running(self, job_id: str) -> JobRecord:
        job = self._require_job(job_id)
        job.mark_running()
        return job

    def mark_succeeded(
        self,
        job_id: str,
        *,
        result: dict[str, Any] | None = None,
        state_after: str | None = None,
    ) -> JobRecord:
        job = self._require_job(job_id)
        job.mark_succeeded(result=result, state_after=state_after)
        return job

    def mark_failed(
        self,
        job_id: str,
        error: ErrorInfo,
        *,
        state_after: str | None = None,
    ) -> JobRecord:
        job = self._require_job(job_id)
        job.mark_failed(error, state_after=state_after)
        return job

    def mark_failed_from_exception(
        self,
        job_id: str,
        exc: ICSException,
        *,
        state_after: str | None = None,
    ) -> JobRecord:
        return self.mark_failed(job_id, exc.info, state_after=state_after)

    def mark_aborted(
        self,
        job_id: str,
        *,
        reason: str = "Job aborted.",
        state_after: str | None = None,
    ) -> JobRecord:
        job = self._require_job(job_id)
        job.mark_aborted(reason=reason, state_after=state_after)
        return job

    def _require_job(self, job_id: str) -> JobRecord:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(f"Unknown job_id: {job_id}")
        return job