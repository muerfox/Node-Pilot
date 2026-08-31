from __future__ import annotations

from celery import shared_task

from apps.jobs.models import Job, JobStatus
from apps.jobs.services import job_run, transition
from apps.jobs.tasks import JobBoundTask
from apps.networks.models import Network, NetworkStatus
from apps.nodes import agent_client
from apps.nodes.protocol import OperationType


@shared_task(bind=True, base=JobBoundTask)
def create_network_task(self, job_id: int, network_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    network = Network.objects.select_related("node", "node__organization").get(pk=network_id)
    try:
        with job_run(job, f"Creating network {network.name}"):
            agent_client.send_operation(
                network.node, OperationType.CREATE_NETWORK, resource_id=str(network.uuid),
                payload={"bridge": network.bridge, "vlan_id": network.vlan_id},
            )
            network.status = NetworkStatus.ACTIVE
            network.save(update_fields=["status"])
        transition(job, JobStatus.SUCCESS, message="Network created")
        _emit(network, "NETWORK_CREATED")
    except Exception as exc:
        network.status = NetworkStatus.ERROR
        network.save(update_fields=["status"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        _emit(network, "NETWORK_ERROR", error=str(exc))
        raise


@shared_task(bind=True, base=JobBoundTask)
def delete_network_task(self, job_id: int, network_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    network = Network.objects.select_related("node", "node__organization").get(pk=network_id)
    try:
        with job_run(job, f"Deleting network {network.name}"):
            agent_client.send_operation(
                network.node, OperationType.DELETE_NETWORK, resource_id=str(network.uuid),
                payload={"bridge": network.bridge, "vlan_id": network.vlan_id},
            )
        network_uuid, network_name, org = network.uuid, network.name, network.node.organization
        network.delete()
        transition(job, JobStatus.SUCCESS, message="Network deleted")
        try:
            from apps.events.services import emit_event

            emit_event(type="NETWORK_DELETED", severity="INFO", resource_type="Network", resource_id=str(network_uuid), organization=org, metadata={"name": network_name})
        except Exception:  # pragma: no cover
            pass
    except Exception as exc:
        network.status = NetworkStatus.ERROR
        network.save(update_fields=["status"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


def _emit(network: Network, event_type: str, **metadata) -> None:
    from apps.events.services import emit_event

    try:
        emit_event(
            type=event_type, severity="INFO" if event_type != "NETWORK_ERROR" else "CRITICAL", resource_type="Network",
            resource_id=str(network.uuid), organization=network.node.organization, metadata={"name": network.name, **metadata},
        )
    except Exception:  # pragma: no cover
        pass
