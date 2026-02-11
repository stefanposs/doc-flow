"""In-memory job repository — dict-based persistence for local dev & testing."""

from __future__ import annotations

import copy

from docflow.domain.models import Job, JobFilter, PaginatedResult
from docflow.domain.ports import JobRepositoryPort


class InMemoryJobRepository(JobRepositoryPort):
    """Job repository backed by a Python dict.

    For production, use a database-backed or Redis-backed implementation.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    async def save(self, job: Job) -> None:
        self._jobs[job.id] = copy.deepcopy(job)

    async def get(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        return copy.deepcopy(job) if job else None

    async def list_jobs(
        self,
        filter_: JobFilter | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResult:
        jobs = list(self._jobs.values())

        if filter_:
            if filter_.status:
                jobs = [j for j in jobs if j.status == filter_.status]
            if filter_.tenant_id:
                jobs = [j for j in jobs if j.tenant_id == filter_.tenant_id]
            if filter_.filename_contains:
                term = filter_.filename_contains.lower()
                jobs = [j for j in jobs if term in j.filename.lower()]
            if filter_.created_after:
                jobs = [j for j in jobs if j.created_at >= filter_.created_after]
            if filter_.created_before:
                jobs = [j for j in jobs if j.created_at <= filter_.created_before]

        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        total = len(jobs)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = jobs[start:end]

        return PaginatedResult(
            items=[copy.deepcopy(j) for j in page_items],
            total=total,
            page=page,
            page_size=page_size,
            has_next=end < total,
        )

    async def delete(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    async def count(self, filter_: JobFilter | None = None) -> int:
        if not filter_:
            return len(self._jobs)
        result = await self.list_jobs(filter_=filter_, page=1, page_size=1)
        return result.total
