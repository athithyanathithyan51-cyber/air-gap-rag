from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import httpx
import pytest

from app.net_guard import NetworkBlockedError, NetworkGuard

# TEST-NET-1 (RFC 5737): reserved, never routed. If the guard failed, the
# connect would time out rather than reach a real host.
UNROUTABLE = "192.0.2.10"


@pytest.fixture
def guard() -> Iterator[NetworkGuard]:
    g = NetworkGuard(allowed=["10.20.0.0/16", "172.30.0.5"])
    g.install()
    try:
        yield g
    finally:
        g.uninstall()


@pytest.fixture
def local_server() -> Iterator[int]:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def accept_once() -> None:
        try:
            conn, _ = srv.accept()
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=accept_once, daemon=True)
    t.start()
    yield port
    srv.close()
    t.join(timeout=2)


def test_blocks_external_ipv4_connect(guard: NetworkGuard) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    with pytest.raises(NetworkBlockedError):
        s.connect((UNROUTABLE, 80))
    s.close()
    assert guard.blocked_count == 1


def test_blocks_connect_ex_and_udp_sendto(guard: NetworkGuard) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(NetworkBlockedError):
        s.connect_ex((UNROUTABLE, 443))
    s.close()
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    with pytest.raises(NetworkBlockedError):
        u.sendto(b"x", ("8.8.8.8", 53))
    u.close()


def test_blocks_dns_resolution_of_external_names(guard: NetworkGuard) -> None:
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("example.com", 443)


def test_blocks_httpx_to_external_host(guard: NetworkGuard) -> None:
    with pytest.raises((NetworkBlockedError, httpx.ConnectError)) as info:
        httpx.get("https://example.com", timeout=1.0, trust_env=False)
    # httpx may wrap the error; either way the root cause must be the guard.
    err: BaseException | None = info.value
    found = False
    while err is not None:
        if isinstance(err, NetworkBlockedError):
            found = True
            break
        err = err.__cause__ or err.__context__
    assert found


def test_allows_loopback(guard: NetworkGuard, local_server: int) -> None:
    s = socket.create_connection(("127.0.0.1", local_server), timeout=2)
    s.close()
    s2 = socket.create_connection(("localhost", local_server), timeout=2)
    s2.close()
    assert guard.blocked_count == 0


def test_allowlist_ip_and_cidr(guard: NetworkGuard) -> None:
    assert guard.host_allowed("172.30.0.5")
    assert guard.host_allowed("10.20.3.4")
    assert not guard.host_allowed("10.21.0.1")
    assert guard.address_allowed(socket.AF_INET, ("::ffff:127.0.0.1", 1))
    assert not guard.address_allowed(socket.AF_INET6, ("2001:db8::1", 80, 0, 0))


def test_binding_wildcard_still_works(guard: NetworkGuard) -> None:
    infos = socket.getaddrinfo("0.0.0.0", 0, socket.AF_INET, socket.SOCK_STREAM)
    assert infos
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("0.0.0.0", 0))
    srv.close()


def test_uninstall_restores_socket_functions() -> None:
    before = (socket.socket.connect, socket.getaddrinfo)
    g = NetworkGuard()
    g.install()
    assert socket.socket.connect is not before[0]
    g.uninstall()
    assert (socket.socket.connect, socket.getaddrinfo) == before
