from __future__ import annotations

import importlib.util
import struct
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_isolation.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_isolation", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ipv4(src: bytes, dst: bytes) -> bytes:
    return bytes([0x45, 0, 0, 20, 0, 0, 0, 0, 64, 6, 0, 0]) + src + dst


def sll2(payload: bytes, ethertype: int = 0x0800, hatype: int = 1) -> bytes:
    return struct.pack("!HHIHBB8s", ethertype, 0, 2, hatype, 0, 6, b"\x00" * 8) + payload


def write_pcap(path: Path, frames: list[bytes], linktype: int = 276) -> None:
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, linktype)
    for i, f in enumerate(frames):
        out += struct.pack("<IIII", 1000 + i, 0, len(f), len(f)) + f
    path.write_bytes(out)


LO = bytes([127, 0, 0, 1])
LAN = bytes([192, 168, 1, 5])
NET = bytes([8, 8, 8, 8])


def test_only_loopback_is_zero(tmp_path: Path) -> None:
    vi = load()
    p = tmp_path / "lo.pcap"
    write_pcap(p, [sll2(ipv4(LO, LO), hatype=772)] * 5)
    r = vi.analyse(str(p))
    assert (r["packets_total"], r["packets_loopback"], r["packets_non_loopback"]) == (5, 5, 0)
    assert vi.main([str(p)]) == 0


def test_external_and_arp_counted(tmp_path: Path) -> None:
    vi = load()
    p = tmp_path / "mixed.pcap"
    write_pcap(p, [sll2(ipv4(LO, LO), hatype=772), sll2(ipv4(LAN, NET)), sll2(b"\x00" * 28, ethertype=0x0806)])
    r = vi.analyse(str(p))
    assert r["packets_non_loopback"] == 2 and r["non_ip_frames"] == 1
    assert any("192.168.1.5 -> 8.8.8.8" in flow for flow, _ in r["top_non_loopback_flows"])
    assert vi.main([str(p)]) == 1


def test_ethernet_linktype_and_bad_input(tmp_path: Path) -> None:
    vi = load()
    p = tmp_path / "eth.pcap"
    eth = b"\x00" * 12 + b"\x08\x00" + ipv4(LO, LO)
    write_pcap(p, [eth], linktype=1)
    assert vi.analyse(str(p))["packets_non_loopback"] == 0
    bad = tmp_path / "bad.pcap"
    bad.write_bytes(b"\x0a\x0d\x0d\x0a" + b"\x00" * 30)
    with pytest.raises(ValueError, match="pcapng"):
        vi.analyse(str(bad))
