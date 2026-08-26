from __future__ import annotations

from urllib.parse import urljoin, urlparse

import click
import httpx

from nodepilot_cli.client import NodePilotClient
from nodepilot_cli.config import load_config


def _origin(api_url: str) -> str:
    parsed = urlparse(api_url)
    return f"{parsed.scheme}://{parsed.netloc}/"


@click.command(name="doctor")
def doctor_command() -> None:
    """Check connectivity to the configured NodePilot controller."""
    config = load_config()
    origin = _origin(config.api_url)
    ok = True

    click.echo(f"Controller: {config.api_url}")

    for label, path in (("Liveness", "health/live/"), ("Readiness", "health/ready/")):
        try:
            response = httpx.get(urljoin(origin, path), verify=config.verify_tls, timeout=10.0)
            healthy = response.status_code < 400
            ok &= healthy
            click.echo(f"  {label}: {'OK' if healthy else f'FAILED ({response.status_code})'}")
        except httpx.HTTPError as exc:
            ok = False
            click.echo(f"  {label}: FAILED ({exc})")

    if not config.token:
        click.echo("  Authentication: NOT CONFIGURED (run `nodepilot login`)")
        ok = False
    else:
        try:
            with NodePilotClient(config) as client:
                me = client.get("users/me/")
            click.echo(f"  Authentication: OK (logged in as {me.get('username')})")
        except Exception as exc:
            ok = False
            click.echo(f"  Authentication: FAILED ({exc})")

    if not ok:
        raise click.exceptions.Exit(1)
    click.secho("All checks passed.", fg="green")
