from __future__ import annotations

import click
from tabulate import tabulate

from nodepilot_cli.client import NodePilotClient


@click.group(name="vm")
def vm_group() -> None:
    """Manage virtual machines."""


@vm_group.command("list")
@click.option("--organization", default=None, help="Filter by organization UUID.")
@click.option("--project", default=None, help="Filter by project UUID.")
@click.option("--status", "status_", default=None, help="Filter by status (e.g. RUNNING, STOPPED).")
@click.pass_obj
def list_vms(config, organization: str | None, project: str | None, status_: str | None) -> None:
    """List virtual machines."""
    params = {k: v for k, v in {"organization": organization, "project": project, "status": status_}.items() if v}
    with NodePilotClient(config) as client:
        rows = [(vm["uuid"], vm["name"], vm["status"], vm["cpu_count"], vm["memory_mb"], vm.get("node") or "-") for vm in client.paginate("vms/", params=params)]
    click.echo(tabulate(rows, headers=["UUID", "Name", "Status", "CPU", "Memory (MB)", "Node"]))


@vm_group.command("start")
@click.argument("vm_uuid")
@click.pass_obj
def start_vm(config, vm_uuid: str) -> None:
    """Start a VM (returns immediately; the operation runs as a
    background job)."""
    with NodePilotClient(config) as client:
        data = client.post(f"vms/{vm_uuid}/start/")
    click.echo(f"job_id: {data['job_id']} (status: {data['status']})")


@vm_group.command("stop")
@click.argument("vm_uuid")
@click.option("--force", is_flag=True, help="Force power-off instead of a graceful shutdown.")
@click.pass_obj
def stop_vm(config, vm_uuid: str, force: bool) -> None:
    """Stop (or, with --force, power off) a VM."""
    with NodePilotClient(config) as client:
        data = client.post(f"vms/{vm_uuid}/stop/", json={"force": force})
    click.echo(f"job_id: {data['job_id']} (status: {data['status']})")


@vm_group.command("reboot")
@click.argument("vm_uuid")
@click.option("--force", is_flag=True, help="Hard reset instead of a graceful reboot.")
@click.pass_obj
def reboot_vm(config, vm_uuid: str, force: bool) -> None:
    """Reboot a VM."""
    with NodePilotClient(config) as client:
        data = client.post(f"vms/{vm_uuid}/reboot/", json={"force": force})
    click.echo(f"job_id: {data['job_id']} (status: {data['status']})")


@vm_group.command("delete")
@click.argument("vm_uuid")
@click.confirmation_option(prompt="This will permanently delete the VM and its disks. Continue?")
@click.pass_obj
def delete_vm(config, vm_uuid: str) -> None:
    """Delete a VM (destructive -- asks for confirmation)."""
    with NodePilotClient(config) as client:
        data = client.delete(f"vms/{vm_uuid}/")
    click.echo(f"job_id: {data.get('job_id')} (status: {data.get('status')})")
