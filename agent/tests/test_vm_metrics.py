from nodepilot_agent.vm_metrics import _DomainCpuTracker


def test_first_sample_returns_none():
    tracker = _DomainCpuTracker()
    assert tracker.sample("dom-1", cpu_time_ns=1_000_000_000, nr_virt_cpu=2) is None


def test_second_sample_computes_percentage(monkeypatch):
    tracker = _DomainCpuTracker()
    times = iter([100.0, 101.0])  # 1 second apart
    monkeypatch.setattr("time.monotonic", lambda: next(times))

    tracker.sample("dom-1", cpu_time_ns=0, nr_virt_cpu=1)
    # 0.5 CPU-seconds of work in 1 wall second on a 1-vCPU domain -> 50%.
    percent = tracker.sample("dom-1", cpu_time_ns=500_000_000, nr_virt_cpu=1)
    assert percent == 50.0


def test_percentage_normalized_across_multiple_vcpus(monkeypatch):
    tracker = _DomainCpuTracker()
    times = iter([100.0, 101.0])
    monkeypatch.setattr("time.monotonic", lambda: next(times))

    tracker.sample("dom-1", cpu_time_ns=0, nr_virt_cpu=4)
    # 2 CPU-seconds of work across 4 vCPUs in 1 wall second -> 50% average utilization.
    percent = tracker.sample("dom-1", cpu_time_ns=2_000_000_000, nr_virt_cpu=4)
    assert percent == 50.0


def test_percentage_capped_at_100(monkeypatch):
    tracker = _DomainCpuTracker()
    times = iter([100.0, 101.0])
    monkeypatch.setattr("time.monotonic", lambda: next(times))

    tracker.sample("dom-1", cpu_time_ns=0, nr_virt_cpu=1)
    percent = tracker.sample("dom-1", cpu_time_ns=5_000_000_000, nr_virt_cpu=1)  # 5 CPU-seconds in 1 wall second
    assert percent == 100.0


def test_negative_delta_is_ignored(monkeypatch):
    """A domain reset or migration can make cpu_time appear to go
    backwards -- must not report a nonsensical negative percentage."""
    tracker = _DomainCpuTracker()
    times = iter([100.0, 101.0])
    monkeypatch.setattr("time.monotonic", lambda: next(times))

    tracker.sample("dom-1", cpu_time_ns=5_000_000_000, nr_virt_cpu=1)
    percent = tracker.sample("dom-1", cpu_time_ns=1_000_000_000, nr_virt_cpu=1)
    assert percent is None


def test_forget_missing_resets_tracking_for_stopped_domains(monkeypatch):
    tracker = _DomainCpuTracker()
    times = iter([100.0, 101.0, 102.0])
    monkeypatch.setattr("time.monotonic", lambda: next(times))

    tracker.sample("dom-1", cpu_time_ns=0, nr_virt_cpu=1)
    tracker.forget_missing(active_domain_uuids=set())  # dom-1 stopped

    # Since tracking was forgotten, this is treated as a first sighting again.
    percent = tracker.sample("dom-1", cpu_time_ns=999, nr_virt_cpu=1)
    assert percent is None
