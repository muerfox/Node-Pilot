from __future__ import annotations

import click

from nodepilot_cli.client import APIError, NodePilotClient
from nodepilot_cli.commands.agent import agent_group
from nodepilot_cli.commands.doctor import doctor_command
from nodepilot_cli.commands.node import node_group
from nodepilot_cli.commands.storage import storage_group
from nodepilot_cli.commands.vm import vm_group
from nodepilot_cli.config import CLIConfig, load_config, save_config


@click.group()
@click.option("--api-url", default=None, help="Override the configured NodePilot API URL.")
@click.option("--token", default=None, help="Override the configured API token.")
@click.pass_context
def cli(ctx: click.Context, api_url: str | None, token: str | None) -> None:
    """nodepilot -- command-line client for the NodePilot API."""
    config = load_config()
    if api_url:
        config.api_url = api_url
    if token:
        config.token = token
    ctx.obj = config


@cli.command()
@click.option("--api-url", prompt="NodePilot API URL", default="https://localhost/api/v1")
@click.option("--token", prompt="API token (from Administration > API Tokens)", hide_input=True)
def login(api_url: str, token: str) -> None:
    """Save API credentials to ~/.config/nodepilot/config.yaml."""
    save_config(CLIConfig(api_url=api_url, token=token, token_type="Token"))
    click.echo("Saved.")


cli.add_command(agent_group, name="agent")
cli.add_command(vm_group, name="vm")
cli.add_command(node_group, name="node")
cli.add_command(storage_group, name="storage")
cli.add_command(doctor_command, name="doctor")


def client_for(ctx: click.Context) -> NodePilotClient:
    return NodePilotClient(ctx.obj)


def handle_api_errors(fn):
    """Decorator: turn APIError into a clean CLI error instead of a
    traceback."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except APIError as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapper


if __name__ == "__main__":
    cli()
