"""Snapshot of the host's non-loopback network interfaces and default routes.

Linux is the supported platform: interface kind comes from /sys/class/net and
default routes from /proc/net/route and /proc/net/ipv6_route. On Windows the
snapshot is best effort (development only; see docs/limits.md).
"""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import subprocess
from pathlib import Path
from typing import Any

import psutil

_CONTAINER_BRIDGE = re.compile(r"^(docker\d*|br-[0-9a-f]+|veth.*|cni\d*|podman\d*|virbr\d*)$")
_RTF_UP = 0x1
_RTF_REJECT = 0x200


def _is_loopback(name: str, addrs: list[Any]) -> bool:
    if name == "lo" or name.lower().startswith("loopback"):
        return True
    ips = [a.address for a in addrs if a.family in (socket.AF_INET, socket.AF_INET6)]
    if not ips:
        return False
    try:
        return all(ipaddress.ip_address(ip.split("%")[0]).is_loopback for ip in ips)
    except ValueError:
        return False


def _kind_linux(name: str, sys_class_net: Path) -> str:
    if _CONTAINER_BRIDGE.match(name):
        return "container-bridge"
    return "physical" if (sys_class_net / name / "device").exists() else "virtual"


def _kind_other(name: str) -> str:
    if _CONTAINER_BRIDGE.match(name) or "vEthernet" in name or "Hyper-V" in name or "WSL" in name:
        return "virtual"
    return "physical"


def default_routes_linux(proc_net: Path = Path("/proc/net")) -> tuple[bool, bool]:
    v4 = v6 = False
    try:
        for line in (proc_net / "route").read_text().splitlines()[1:]:
            f = line.split()
            if len(f) >= 8 and f[1] == "00000000" and f[7] == "00000000":
                flags = int(f[3], 16)
                if flags & _RTF_UP and not flags & _RTF_REJECT:
                    v4 = True
    except OSError:
        pass
    try:
        for line in (proc_net / "ipv6_route").read_text().splitlines():
            f = line.split()
            if len(f) >= 10 and f[0] == "0" * 32 and f[1] == "00" and f[9] != "lo":
                flags = int(f[8], 16)
                if flags & _RTF_UP and not flags & _RTF_REJECT:
                    v6 = True
    except OSError:
        pass
    return v4, v6


def default_routes_windows() -> tuple[bool, bool]:
    def has_default(args: list[str], pattern: str) -> bool:
        try:
            out = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False).stdout  # noqa: S603
        except (OSError, subprocess.SubprocessError):
            return False
        return re.search(pattern, out, re.M) is not None

    any_v4 = "0.0.0.0"  # noqa: S104 - a route query, not a bind
    v4 = has_default(["route", "print", "-4", any_v4], r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+\S+")
    v6 = has_default(["route", "print", "-6", "::/0"], r"^\s*\d+\s+\d+\s+::/0\s")
    return v4, v6


LINK_DOWN_STATES = frozenset({"down", "lowerlayerdown", "notpresent"})


def operstate(name: str, sys_class_net: Path = Path("/sys/class/net")) -> str:
    """Kernel RFC 2863 operational state: up, down, dormant, lowerlayerdown, notpresent, testing, unknown."""
    try:
        return (sys_class_net / name / "operstate").read_text().strip() or "unknown"
    except OSError:
        return "unknown"


def snapshot(sys_class_net: Path = Path("/sys/class/net"), proc_net: Path = Path("/proc/net")) -> dict[str, Any]:
    system = platform.system().lower()
    stats = psutil.net_if_stats()
    all_addrs = psutil.net_if_addrs()
    interfaces = []
    for name in sorted(set(stats) | set(all_addrs)):
        addrs = all_addrs.get(name, [])
        if _is_loopback(name, addrs):
            continue
        st = stats.get(name)
        ips = sorted(a.address for a in addrs if a.family in (socket.AF_INET, socket.AF_INET6))
        admin_up = bool(st.isup) if st else False
        oper = operstate(name, sys_class_net) if system == "linux" else ("up" if admin_up else "down")
        interfaces.append(
            {
                "name": name,
                # Can carry traffic: administratively up AND the link is not down (cable/carrier present).
                "up": admin_up and oper not in LINK_DOWN_STATES,
                "admin_up": admin_up,
                "oper": oper,
                "addrs": ips,
                "kind": _kind_linux(name, sys_class_net) if system == "linux" else _kind_other(name),
            }
        )
    v4, v6 = default_routes_linux(proc_net) if system == "linux" else default_routes_windows()
    return {
        "platform": system,
        "interfaces": interfaces,
        "default_route_v4": v4,
        "default_route_v6": v6,
    }
