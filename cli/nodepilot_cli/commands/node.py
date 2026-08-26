from __future__ import annotations

import click
from tabulate import tabulate

from nodepilot_cli.client import NodePilotClient


@click.group(name="node")
def node_group() -> None:
    """Manage hypervisor nodes."""


@node_group.command("list")
@click.option("--organization", default=None, help="Filter by organization UUID.")
@click.pass_obj
def list_nodes(config, organization: str | None) -> None:
    """List hypervisor nodes."""
    params = {"organization": organization} if organization else {}
    with NodePilotClient(config) as client:
        rows = [
            (n["uuid"], n["name"], n["status"], n["cpu_cores"], f"{n['memory_available_mb']}/{n['memory_total_mb']}", f"{n['storage_available_gb']}/{n['storage_total_gb']}")
            for n in client.paginate("nodes/", params=params)
        ]
    click.echo(tabulate(rows, headers=["UUID", "Name", "Status", "Cores", "Mem free/total MB", "Storage free/total GB"]))
