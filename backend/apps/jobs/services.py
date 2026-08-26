from __future__ import annotations

import contextlib
import logging

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import InvalidStateTransition
from apps.jobs.models import VALID_TRANSITIONS, Job, JobStatus

logger = logging.getLogger("nodepilot.jobs")


class JobCancelled(Exception):
    """Raised inside a task body when cooperative cancellation is observed."""


def create_job(
    *,
    type: str,
    resource_type: str,
    organization,
    created_by,
    resource_id: str = "",
    node=None,
    idempotency_key: str = "",
    timeout_seconds: int = 600,
) -> Job:
    return Job.objects.create(
        type=type,
        resource_type=resource_type,
        resource_id=resource_id,
        organization=organization,
        node=node,
        created_by=created_by,
        idempotency_key=idempotency_key,
        timeout_seconds=timeout_seconds,
        status=JobStatus.QUEUED,
    )


def _broadcast(job: Job) -> None:
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"job.{job.uuid}",
            {
                "type": "job.update",
                "job": {
                    "uuid": str(job.uuid),
                    "status": job.status,
                    "progress": job.progress,
                    "message": job.message,
                    "error": job.error,
                },
            },
        )
    except Exception:  # pragma: no cover - broadcasting must never break the job.
        logger.exception("Failed to broadcast job update for %s", job.uuid)


@transaction.atomic
def transition(job: Job, new_status: str, *, message: str | None = None, error: str | None = None) -> Job:
    locked = Job.objects.select_for_update().get(pk=job.pk)
    allowed = VALID_TRANSITIONS.get(locked.status, set())
    if new_status not in allowed and new_status != locked.status:
        raise InvalidStateTransition(f"Cannot transition job from {locked.status} to {new_status}")

    locked.status = new_status
    if message is not None:
        locked.message = message
    if error is not None:
        locked.error = error
    if new_status == JobStatus.RUNNING and locked.started_at is None:
        locked.started_at = timezone.now()
    if new_status in {JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELED}:
        locked.finished_at = timezone.now()
        if new_status == JobStatus.SUCCESS:
            locked.progress = 100
    locked.save()
    _broadcast(locked)
    return locked


def set_progress(job: Job, progress: int, message: str | None = None) -> Job:
    job.progress = max(0, min(100, progress))
    if message is not None:
        job.message = message
    job.save(update_fields=["progress", "message", "updated_at"])
    _broadcast(job)
    return job


def append_log(job: Job, line: str) -> None:
    Job.objects.filter(pk=job.pk).update(logs=Job.objects.get(pk=job.pk).logs + [{"at": timezone.now().isoformat(), "line": line}])


def request_cancel(job: Job) -> Job:
    from celery import current_app

    if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise InvalidStateTransition(f"Job in status {job.status} cannot be canceled")

    updated = transition(job, JobStatus.CANCELING, message="Cancellation requested")
    if updated.celery_task_id:
        current_app.control.revoke(updated.celery_task_id, terminate=False)
    return updated


def is_cancel_requested(job_id: int) -> bool:
    return Job.objects.filter(pk=job_id, status=JobStatus.CANCELING).exists()


@contextlib.contextmanager
def job_run(job: Job, step: str | None = None):
    """
    Wraps a unit of task work: marks the job RUNNING on enter (first call
    only), checks for cooperative cancellation, and marks SUCCESS/FAILED on
    exit based on whether an exception propagated.

        with job_run(job, "Creating disk"):
            agent_client.create_disk(...)
    """
    if job.status == JobStatus.QUEUED:
        transition(job, JobStatus.RUNNING)
    if is_cancel_requested(job.pk):
        raise JobCancelled(f"Job {job.uuid} was canceled")
    if step:
        set_progress(job, job.progress, step)
        append_log(job, step)
    try:
        yield
    except JobCancelled:
        transition(job, JobStatus.CANCELED, message="Canceled")
        raise
    except Exception as exc:
        transition(job, JobStatus.FAILED, error=str(exc))
        raise
