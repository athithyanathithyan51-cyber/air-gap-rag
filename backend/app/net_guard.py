"""In-process egress guard.

Patches the Python socket layer so this process can only connect to loopback
addresses, Unix sockets, and an explicit allowlist of hosts/IPs/CIDRs (for
example the Qdrant and Ollama containers). Any other connect, connect_ex,
sendto, or DNS lookup raises NetworkBlockedError and is logged.

Limits (documented in docs/limits.md): this covers code that uses Python's
socket module (httpx, urllib, asyncio, qdrant-client). Native extensions that
open sockets directly from C, and other processes on the host, are not covered.
OS-level enforcement (nftables) is the complementary control.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
from collections.abc import Iterable
from typing import Any

log = logging.getLogger("airgap.net_guard")

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"})


class NetworkBlockedError(PermissionError):
    """Raised when code attempts a connection outside the allowlist."""


def _parse_ip(value: str) -> IPAddress | None:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


class NetworkGuard:
    def __init__(self, allowed: Iterable[str] = ()) -> None:
        self._lock = threading.Lock()
        self._allowed_names: set[str] = set()
        self._allowed_nets: list[IPNetwork] = []
        self._allowed_ips: set[IPAddress] = set()
        self.blocked_count = 0
        self._installed = False
        self._orig: dict[str, Any] = {}
        for entry in allowed:
            self._add_allowed(entry.strip())

    def _add_allowed(self, entry: str) -> None:
        if not entry:
            return
        if "/" in entry:
            self._allowed_nets.append(ipaddress.ip_network(entry, strict=False))
            return
        ip = _parse_ip(entry)
        if ip is not None:
            self._allowed_ips.add(ip)
        else:
            self._allowed_names.add(entry.lower().rstrip("."))

    # ---- policy -------------------------------------------------------------

    def host_allowed(self, host: str) -> bool:
        name = host.lower().rstrip(".")
        if name in _LOOPBACK_NAMES or name in self._allowed_names:
            return True
        ip = _parse_ip(name)
        return ip is not None and self.ip_allowed(ip)

    def ip_allowed(self, ip: IPAddress) -> bool:
        if ip.is_loopback:
            return True
        with self._lock:
            if ip in self._allowed_ips:
                return True
            return any(ip.version == net.version and ip in net for net in self._allowed_nets)

    def address_allowed(self, family: int, address: Any) -> bool:
        if family == getattr(socket, "AF_UNIX", object()):
            return True
        if family not in (socket.AF_INET, socket.AF_INET6):
            return False
        if not isinstance(address, tuple) or not address:
            return False
        ip = _parse_ip(str(address[0]))
        if ip is None:
            # A hostname passed straight to connect() is resolved by the OS; check the name.
            return self.host_allowed(str(address[0]))
        return self.ip_allowed(ip)

    def _block(self, what: str, target: Any) -> NetworkBlockedError:
        self.blocked_count += 1
        log.warning("network_blocked", extra={"op": what, "target": str(target)})
        return NetworkBlockedError(f"network access blocked by air-gap guard: {what} {target!r}")

    # ---- install / uninstall -------------------------------------------------

    def install(self) -> None:
        if self._installed:
            return
        guard = self
        orig_connect = socket.socket.connect
        orig_connect_ex = socket.socket.connect_ex
        orig_sendto = socket.socket.sendto
        orig_getaddrinfo = socket.getaddrinfo
        self._orig = {
            "connect": orig_connect,
            "connect_ex": orig_connect_ex,
            "sendto": orig_sendto,
            "getaddrinfo": orig_getaddrinfo,
        }

        def connect(sock: socket.socket, address: Any) -> None:
            if not guard.address_allowed(sock.family, address):
                raise guard._block("connect", address)
            orig_connect(sock, address)

        def connect_ex(sock: socket.socket, address: Any) -> int:
            if not guard.address_allowed(sock.family, address):
                raise guard._block("connect_ex", address)
            return int(orig_connect_ex(sock, address))

        def sendto(sock: socket.socket, data: Any, *args: Any) -> int:
            address = args[-1]
            if not guard.address_allowed(sock.family, address):
                raise guard._block("sendto", address)
            return int(orig_sendto(sock, data, *args))

        def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
            if host is None:
                return orig_getaddrinfo(host, *args, **kwargs)
            name = host.decode() if isinstance(host, bytes) else str(host)
            if _parse_ip(name) is not None or name == "":
                # IP literals need no DNS; connect() enforces policy. Servers also
                # call getaddrinfo("0.0.0.0") to bind, which must keep working.
                return orig_getaddrinfo(host, *args, **kwargs)
            if not guard.host_allowed(name):
                raise guard._block("resolve", name)
            results = orig_getaddrinfo(host, *args, **kwargs)
            if name.lower().rstrip(".") in guard._allowed_names:
                with guard._lock:
                    for _fam, _type, _proto, _canon, sockaddr in results:
                        ip = _parse_ip(str(sockaddr[0]))
                        if ip is not None:
                            guard._allowed_ips.add(ip)
            return results

        socket.socket.connect = connect  # type: ignore[method-assign,assignment]
        socket.socket.connect_ex = connect_ex  # type: ignore[method-assign,assignment]
        socket.socket.sendto = sendto  # type: ignore[method-assign,assignment]
        socket.getaddrinfo = getaddrinfo
        self._installed = True
        log.info(
            "net_guard_installed",
            extra={
                "allowed_names": sorted(self._allowed_names),
                "allowed_ips": sorted(str(i) for i in self._allowed_ips),
                "allowed_nets": [str(n) for n in self._allowed_nets],
            },
        )

    def uninstall(self) -> None:
        if not self._installed:
            return
        socket.socket.connect = self._orig["connect"]  # type: ignore[method-assign]
        socket.socket.connect_ex = self._orig["connect_ex"]  # type: ignore[method-assign]
        socket.socket.sendto = self._orig["sendto"]  # type: ignore[method-assign]
        socket.getaddrinfo = self._orig["getaddrinfo"]
        self._installed = False

    @property
    def installed(self) -> bool:
        return self._installed


_active: NetworkGuard | None = None


def install_guard(allowed: Iterable[str]) -> NetworkGuard:
    """Install a process-wide guard once; later calls return the active guard."""
    global _active
    if _active is None:
        _active = NetworkGuard(allowed)
        _active.install()
    return _active


def active_guard() -> NetworkGuard | None:
    return _active
