"""Live traffic meter for the isolation demo.

While the monitor says the machine is isolated, sums the OS byte/packet counters of every
interface that is NOT on the isolation allowlist (Wi-Fi, Ethernet, tunnels...) from the moment
isolation began, and lists this process's sockets to non-loopback addresses. Both should stay at
zero. Like the snapshot, this is evidence about interfaces and sockets at sampling time, not a
packet capture; scripts/capture-windows.ps1 is the stronger evidence.
"""

from __future__ import annotations

import ipaddress
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import psutil

from attestation.verify_chain import _matches

Counters = tuple[int, int, int, int]  # bytes_sent, bytes_recv, packets_sent, packets_recv
CountersFn = Callable[[], dict[str, Counters]]
RemotesFn = Callable[[], list[str]]


def os_counters() -> dict[str, Counters]:
    return {
        name: (c.bytes_sent, c.bytes_recv, c.packets_sent, c.packets_recv)
        for name, c in psutil.net_io_counters(pernic=True).items()
    }


def _is_local(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip.split("%")[0]).is_loopback
    except ValueError:
        return False


def own_remote_sockets() -> list[str]:
    """This process's inet sockets whose remote end is not loopback, as "ip:port"."""
    try:
        conns = psutil.Process().net_connections(kind="inet")
    except (psutil.Error, OSError):
        return []
    return sorted({f"{c.raddr.ip}:{c.raddr.port}" for c in conns if c.raddr and not _is_local(c.raddr.ip)})


class TrafficMeter:
    def __init__(self, counters: CountersFn = os_counters, remotes: RemotesFn = own_remote_sockets) -> None:
        self._counters = counters
        self._remotes = remotes
        self._lock = threading.Lock()
        self._since: str | None = None
        self._base: dict[str, Counters] = {}
        self._totals: Counters = (0, 0, 0, 0)
        self._external: list[str] = []
        self._app_remotes: list[str] = []

    def update(self, net: dict[str, Any], isolated: bool, allow: list[str]) -> None:
        external = sorted(
            str(i.get("name", "")) for i in net.get("interfaces", []) if not _matches(str(i.get("name", "")), allow)
        )
        cur = self._counters()
        remotes = self._remotes()
        with self._lock:
            self._external = external
            self._app_remotes = remotes
            if not isolated:
                self._since, self._base, self._totals = None, {}, (0, 0, 0, 0)
                return
            if self._since is None:
                self._since = datetime.now(UTC).isoformat(timespec="seconds")
                self._base = dict(cur)
            totals = [0, 0, 0, 0]
            for name in external:
                now = cur.get(name, (0, 0, 0, 0))
                base = self._base.get(name, (0, 0, 0, 0))
                for k in range(4):
                    # An adapter reset restarts its counters; count from zero rather than go negative.
                    totals[k] += now[k] - base[k] if now[k] >= base[k] else now[k]
            self._totals = (totals[0], totals[1], totals[2], totals[3])

    def status(self) -> dict[str, Any]:
        with self._lock:
            sent_b, recv_b, sent_p, recv_p = self._totals
            return {
                "since": self._since,
                "sent_bytes": sent_b,
                "recv_bytes": recv_b,
                "sent_packets": sent_p,
                "recv_packets": recv_p,
                "interfaces": list(self._external),
                "app_remote_sockets": list(self._app_remotes),
            }
