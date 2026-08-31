"""
Regression coverage for VLAN network isolation: previously the `vlan`
field the controller sends on every NIC payload was read nowhere on the
agent side (no <vlan> XML, no separate bridge), so two VM NICs on
supposedly VLAN-separated networks that happened to share the same base
bridge string ended up on the exact same untagged L2 segment -- no
isolation at all despite the platform presenting VLANs as configured and
enforced. ensure_vlan_network/teardown_vlan_network give every VLAN a
dedicated bridge (uplinked through a tagged 802.1Q sub-interface on the
parent), and _resolve_nic_bridge/_nic_target_bridge route NIC attachment
to that dedicated bridge instead of the raw parent.
"""
from __future__ import annotations

import subprocess

import pytest

from nodepilot_agent import network


class _RecordingRun:
    """Stands in for network._run: records every invocation and reports
    "nothing exists yet" for any existence check, so create_* calls take
    their real (recorded) code path instead of short-circuiting."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, args, check=True):
        self.calls.append(args)
        if "show" in args:
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="")
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


@pytest.fixture
def recorder(monkeypatch):
    fake = _RecordingRun()
    monkeypatch.setattr(network, "_run", fake)
    return fake


def test_vlan_bridge_name_is_distinct_from_the_uplink_interface_name():
    uplink = network.vlan_interface_name("vmbr0", 120)
    bridge = network.vlan_bridge_name("vmbr0", 120)
    assert uplink == "vmbr0.120"
    assert bridge == "vmbr0.120b"
    assert uplink != bridge


def test_ensure_vlan_network_creates_parent_bridge_uplink_and_dedicated_bridge(recorder):
    result = network.ensure_vlan_network("vmbr0", 120)

    assert result == "vmbr0.120b"
    flat = [" ".join(c) for c in recorder.calls]
    assert any("add name vmbr0 type bridge" in c for c in flat)
    assert any("add link vmbr0 name vmbr0.120 type vlan id 120" in c for c in flat)
    assert any("add name vmbr0.120b type bridge" in c for c in flat)
    assert any("set vmbr0.120 master vmbr0.120b" in c for c in flat)


def test_ensure_vlan_network_is_idempotent_on_retry(monkeypatch):
    """A retried CREATE_NETWORK (Celery retry, or an idempotency-key
    resend) must not blow up with "File exists" from a raw `ip link add`
    on something that's already there."""

    def already_exists(args, check=True):
        if "show" in args:
            return subprocess.CompletedProcess(args, returncode=0, stdout='[{"ifname":"x"}]', stderr="")
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(network, "_run", already_exists)

    result = network.ensure_vlan_network("vmbr0", 120)
    assert result == "vmbr0.120b"  # no exception despite everything already existing


def test_teardown_vlan_network_removes_the_dedicated_bridge_and_uplink_but_not_the_parent(recorder):
    network.teardown_vlan_network("vmbr0", 120)

    flat = [" ".join(c) for c in recorder.calls]
    assert any("delete vmbr0.120b type bridge" in c for c in flat)
    assert any("delete vmbr0.120" in c and "vmbr0.120b" not in c for c in flat)
    assert not any("delete vmbr0 type bridge" in c for c in flat)  # parent untouched


def test_resolve_nic_bridge_targets_the_dedicated_bridge_when_a_vlan_is_set():
    from nodepilot_agent.domain_xml import _resolve_nic_bridge

    assert _resolve_nic_bridge({"bridge": "vmbr0", "vlan": 120}) == "vmbr0.120b"


def test_resolve_nic_bridge_targets_the_raw_bridge_when_no_vlan_is_set():
    from nodepilot_agent.domain_xml import _resolve_nic_bridge

    assert _resolve_nic_bridge({"bridge": "vmbr0"}) == "vmbr0"
    assert _resolve_nic_bridge({"bridge": "vmbr0", "vlan": None}) == "vmbr0"


def test_two_vlans_on_the_same_parent_bridge_resolve_to_different_dedicated_bridges():
    """The actual isolation property: two networks that only differ by
    vlan_id must never resolve to the same attachment target."""
    from nodepilot_agent.domain_xml import _resolve_nic_bridge

    a = _resolve_nic_bridge({"bridge": "vmbr0", "vlan": 100})
    b = _resolve_nic_bridge({"bridge": "vmbr0", "vlan": 200})
    assert a != b


def test_build_domain_xml_nic_uses_the_resolved_vlan_bridge():
    from nodepilot_agent.domain_xml import build_domain_xml

    xml = build_domain_xml(
        {
            "name": "vm1", "domain_uuid": "11111111-1111-1111-1111-111111111111", "memory_mb": 1024,
            "nics": [{"bridge": "vmbr0", "vlan": 120, "mac_address": "52:54:00:00:00:01"}],
        }
    )
    assert 'source bridge="vmbr0.120b"' in xml
    assert 'source bridge="vmbr0"' not in xml
