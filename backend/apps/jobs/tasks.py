from __future__ import annotations

import logging

from celery import Task

logger = logging.getLogger("nodepilot.jobs")


class JobBoundTask(Task):
    """
    Base class for Celery tasks that execute a Job. Records the Celery
    task_id on the Job row (so `request_cancel` can revoke it) and ensures
    an unhandled exception still leaves the Job in a terminal FAILED state
    instead of silently vanishing.
    """

    autoretry_for = ()
    max_retries = 0

    def before_start(self, task_id, args, kwargs):
        job_id = kwargs.get("job_id") or (args[0] if args else None)
        if job_id is None:
            return
        from apps.jobs.models import Job

        Job.objects.filter(pk=job_id).update(celery_task_id=task_id)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = kwargs.get("job_id") or (args[0] if args else None)
        if job_id is None:
            return
        from apps.jobs.models import Job, JobStatus
        from apps.jobs.services import transition

        job = Job.objects.filter(pk=job_id).first()
        if job and not job.is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        logger.error("Job %s failed: %s", job_id, exc, exc_info=einfo)
