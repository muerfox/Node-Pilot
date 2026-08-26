from __future__ import annotations

import click
from tabulate import tabulate

from nodepilot_cli.client import NodePilotClient


@click.group(name="storage")
def storage_group() -> None:
    """Manage storage pools."""


@storage_group.command("list")
@click.option("--node", default=None, help="Filter by node UUID.")
@click.pass_obj
def list_storage(config, node: str | None) -> None:
    """List storage pools."""
    params = {"node": node} if node else {}
    with NodePilotClient(config) as client:
        rows = [
            (s["uuid"], s["name"], s["type"], s["status"], s["available_bytes"] // (1024**3), "yes" if s["shared"] else "no")
            for s in client.paginate("storages/", params=params)
        ]
    click.echo(tabulate(rows, headers=["UUID", "Name", "Type", "Status", "Free GB", "Shared"]))
