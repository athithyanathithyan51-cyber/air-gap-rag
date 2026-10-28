from __future__ import annotations

import socket
import struct
from pathlib import Path

import pytest

from traffic.pcap import read_packets, summarize

SRC, DST = "10.0.0.5", "93.184.216.34"
EPOCH = 1_700_000_000


def tcp_syn_frame(sport: int = 50000, dport: int = 443) -> bytes:
    eth = b"\x02\x00\x00\x00\x00\x02" + b"\x02\x00\x00\x00\x00\x01" + struct.pack("!H", 0x0800)
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 40, 1, 0, 64, 6, 0, socket.inet_aton(SRC), socket.inet_aton(DST))
    tcp = struct.pack("!HHIIBBHHH", sport, dport, 1, 0, 0x50, 0x02, 65535, 0, 0)
    return eth + ip + tcp


def classic_file(path: Path, frames: list[bytes]) -> Path:
    data = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    for n, frame in enumerate(frames):
        data += struct.pack("<IIII", EPOCH, 500_000 + n, len(frame), len(frame)) + frame
    path.write_bytes(data)
    return path


def pcapng_file(path: Path, frame: bytes) -> Path:
    shb = struct.pack("<IIIHHq", 0x0A0D0D0A, 28, 0x1A2B3C4D, 1, 0, -1) + struct.pack("<I", 28)
    idb = struct.pack("<IIHHI", 1, 20, 1, 0, 65535) + struct.pack("<I", 20)
    units = EPOCH * 1_000_000 + 500_000  # default timestamp resolution is microseconds
    padded = frame + b"\x00" * (-len(frame) % 4)
    total = 12 + 20 + len(padded)
    epb = (
        struct.pack("<II", 6, total)
        + struct.pack("<IIIII", 0, units >> 32, units & 0xFFFFFFFF, len(frame), len(frame))
        + padded
        + struct.pack("<I", total)
    )
    path.write_bytes(shb + idb + epb)
    return path


def test_classic_capture_is_decoded(tmp_path: Path) -> None:
    packets = list(read_packets(classic_file(tmp_path / "c.pcap", [tcp_syn_frame()])))
    assert len(packets) == 1
    p = packets[0]
    assert (p.src, p.dst, p.protocol, p.ports, p.info) == (SRC, DST, "HTTPS", "50000 -> 443", "SYN")
    assert p.time == pytest.approx(EPOCH + 0.5)


def test_pcapng_capture_is_decoded(tmp_path: Path) -> None:
    packets = list(read_packets(pcapng_file(tmp_path / "c.pcapng", tcp_syn_frame())))
    assert len(packets) == 1
    p = packets[0]
    assert (p.src, p.dst, p.protocol, p.info) == (SRC, DST, "HTTPS", "SYN")
    assert p.time == pytest.approx(EPOCH + 0.5)


def test_summary_counts_protocols_and_talkers(tmp_path: Path) -> None:
    frames = [tcp_syn_frame(dport=443), tcp_syn_frame(dport=80), tcp_syn_frame(dport=443)]
    s = summarize(classic_file(tmp_path / "s.pcap", frames))
    assert s.packets == 3
    assert dict(s.protocols) == {"HTTPS": 2, "HTTP": 1}
    assert s.talkers[SRC] == 3 and s.talkers[DST] == 3
    assert s.bytes == sum(len(f) for f in frames)
    assert not s.truncated


def test_unknown_file_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pcap"
    bad.write_bytes(b"this is not a capture file at all")
    with pytest.raises(ValueError):
        list(read_packets(bad))
