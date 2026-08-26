import pytest

from apps.common.exceptions import InvalidStateTransition
from apps.jobs.models import JobStatus, JobType
from apps.jobs.services import create_job, job_run, request_cancel, transition

pytestmark = pytest.mark.django_db


def _job(organization):
    return create_job(type=JobType.VM_START, resource_type="VirtualMachine", organization=organization, created_by=None)


def test_queued_to_running_to_success(organization):
    job = _job(organization)
    assert job.status == JobStatus.QUEUED

    job = transition(job, JobStatus.RUNNING)
    assert job.status == JobStatus.RUNNING
    assert job.started_at is not None

    job = transition(job, JobStatus.SUCCESS)
    assert job.status == JobStatus.SUCCESS
    assert job.progress == 100
    assert job.finished_at is not None


def test_illegal_transition_is_rejected(organization):
    job = _job(organization)
    with pytest.raises(InvalidStateTransition):
        transition(job, JobStatus.SUCCESS)  # QUEUED must go through RUNNING first


def test_terminal_job_cannot_transition_again(organization):
    job = _job(organization)
    job = transition(job, JobStatus.RUNNING)
    job = transition(job, JobStatus.SUCCESS)  # terminal
    with pytest.raises(InvalidStateTransition):
        transition(job, JobStatus.RUNNING)


def test_job_run_marks_failed_on_exception(organization):
    job = _job(organization)
    with pytest.raises(ValueError):
        with job_run(job, "doing the thing"):
            raise ValueError("boom")

    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert "boom" in job.error


def test_job_run_success_path_transitions_to_running(organization):
    job = _job(organization)
    with job_run(job, "step one"):
        pass
    job.refresh_from_db()
    assert job.status == JobStatus.RUNNING  # job_run itself never marks SUCCESS -- the task does, after all steps
    assert job.progress == 0
    assert job.message == "step one"


def test_cancel_queued_job(organization):
    job = _job(organization)
    updated = request_cancel(job)
    assert updated.status == JobStatus.CANCELING


def test_cancel_terminal_job_rejected(organization):
    job = _job(organization)
    job = transition(job, JobStatus.RUNNING)
    job = transition(job, JobStatus.SUCCESS)
    with pytest.raises(InvalidStateTransition):
        request_cancel(job)
