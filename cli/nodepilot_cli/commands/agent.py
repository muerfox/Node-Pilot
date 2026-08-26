from __future__ import annotations

import click
from tabulate import tabulate

from nodepilot_cli.client import NodePilotClient


@click.group(name="agent")
def agent_group() -> None:
    """Manage node agent identities."""


@agent_group.command("register")
@click.argument("node_uuid")
@click.pass_obj
def register(config, node_uuid: str) -> None:
    """Issue a fresh agent token for a node. Prints the token exactly
    once -- put it in that node's /etc/nodepilot/agent.yaml."""
    with NodePilotClient(config) as client:
        data = client.post(f"nodes/{node_uuid}/register-agent/")
    click.echo(f"node_id:   {data['node_id']}")
    click.echo(f"agent_id:  {data['agent_id']}")
    click.echo(f"token:     {data['token']}")
    click.secho("Store this token now -- it will not be shown again.", fg="yellow")


@agent_group.command("status")
@click.argument("node_uuid")
@click.pass_obj
def status(config, node_uuid: str) -> None:
    """Show a node's agent connection/heartbeat status."""
    with NodePilotClient(config) as client:
        node = client.get(f"nodes/{node_uuid}/")
    agent = node.get("agent") or {}
    rows = [
        ("Node", node["name"]),
        ("Status", node["status"]),
        ("Agent status", agent.get("status", "NOT REGISTERED")),
        ("Agent version", node.get("agent_version") or "-"),
        ("Last heartbeat", agent.get("last_heartbeat_at") or "never"),
    ]
    click.echo(tabulate(rows, tablefmt="plain"))
