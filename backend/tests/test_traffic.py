from __future__ import annotations

from typing import Any

from attestation.traffic import Counters, TrafficMeter, own_remote_sockets

ALLOW = ["docker0", "vEthernet (WSL*"]


def net(*names: str) -> dict[str, Any]:
    return {"interfaces": [{"name": n, "up": False, "kind": "physical"} for n in names]}


class FakeCounters:
    def __init__(self) -> None:
        self.values: dict[str, Counters] = {}

    def __call__(self) -> dict[str, Counters]:
        return dict(self.values)


def test_counts_only_external_interfaces_from_when_isolation_began() -> None:
    c = FakeCounters()
    c.values = {"Wi-Fi": (5000, 9000, 50, 90), "vEthernet (WSL)": (100, 100, 1, 1)}
    m = TrafficMeter(c, lambda: [])
    n = net("Wi-Fi", "vEthernet (WSL)")
    m.update(n, isolated=False, allow=ALLOW)
    assert m.status()["since"] is None
    m.update(n, isolated=True, allow=ALLOW)
    c.values = {"Wi-Fi": (5000, 9000, 50, 90), "vEthernet (WSL)": (900, 900, 9, 9)}  # internal traffic only
    m.update(n, isolated=True, allow=ALLOW)
    s = m.status()
    assert s["since"] and s["interfaces"] == ["Wi-Fi"]
    assert (s["sent_bytes"], s["recv_bytes"], s["sent_packets"], s["recv_packets"]) == (0, 0, 0, 0)
    c.values["Wi-Fi"] = (5060, 9000, 1, 90)  # 60 B leaked; packet counter reset by an adapter restart
    m.update(n, isolated=True, allow=ALLOW)
    s = m.status()
    assert (s["sent_bytes"], s["recv_bytes"], s["sent_packets"], s["recv_packets"]) == (60, 0, 1, 0)


def test_going_online_resets_and_reports_app_sockets() -> None:
    c = FakeCounters()
    c.values = {"Wi-Fi": (0, 0, 0, 0)}
    m = TrafficMeter(c, lambda: ["93.184.216.34:443"])
    m.update(net("Wi-Fi"), isolated=True, allow=ALLOW)
    c.values = {"Wi-Fi": (10, 10, 1, 1)}
    m.update(net("Wi-Fi"), isolated=False, allow=ALLOW)
    s = m.status()
    assert s["since"] is None and s["sent_bytes"] == 0
    assert s["app_remote_sockets"] == ["93.184.216.34:443"]


def test_monitor_status_includes_traffic(env: Any) -> None:
    mon = env.services.monitor
    mon.traffic = TrafficMeter(FakeCounters(), lambda: [])
    mon.check_once()
    t = mon.status()["traffic"]
    assert t["since"] is not None and t["sent_bytes"] == 0


def test_own_remote_sockets_runs() -> None:
    assert isinstance(own_remote_sockets(), list)
