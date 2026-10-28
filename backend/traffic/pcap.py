"""Reads packet captures for the Traffic view: classic libpcap and pcapng, no third-party packages.

Decodes Ethernet (with VLAN tags), Linux cooked captures and raw IP into IPv4/IPv6, TCP, UDP and
ICMP headers. Anything it does not understand is still listed, with its EtherType as protocol.
"""

from __future__ import annotations

import socket
import struct
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LINKTYPE_ETHERNET, LINKTYPE_RAW, LINKTYPE_LINUX_SLL, LINKTYPE_LINUX_SLL2 = 1, 101, 113, 276
ETH_IPV4, ETH_IPV6, ETH_ARP, ETH_VLAN = 0x0800, 0x86DD, 0x0806, 0x8100
PCAPNG_SHB = b"\x0a\x0d\x0d\x0a"
PCAPNG_BOM = b"\x4d\x3c\x2b\x1a"  # byte-order magic, read in the file's own order

SERVICES = {
    20: "FTP", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 67: "DHCP", 68: "DHCP", 80: "HTTP",
    88: "Kerberos", 110: "POP3", 123: "NTP", 135: "RPC", 137: "NetBIOS", 138: "NetBIOS", 139: "NetBIOS",
    143: "IMAP", 389: "LDAP", 443: "HTTPS", 445: "SMB", 465: "SMTPS", 587: "SMTP", 636: "LDAPS", 993: "IMAPS",
    995: "POP3S", 1900: "SSDP", 3389: "RDP", 5353: "mDNS", 5355: "LLMNR", 8000: "HTTP", 8080: "HTTP",
}
IP_PROTO_NAMES = {1: "ICMP", 6: "TCP", 17: "UDP", 58: "ICMPv6"}


@dataclass
class Packet:
    number: int
    time: float  # seconds since the epoch
    length: int
    src: str
    dst: str
    protocol: str
    ports: str = ""  # "sport -> dport" for TCP and UDP
    info: str = ""  # TCP flags, ICMP type, and similar


@dataclass
class Summary:
    packets: int = 0
    bytes: int = 0
    first: float | None = None
    last: float | None = None
    protocols: Counter[str] = field(default_factory=Counter)
    talkers: Counter[str] = field(default_factory=Counter)
    truncated: bool = False


def _ip_text(raw: bytes) -> str:
    return socket.inet_ntop(socket.AF_INET6 if len(raw) == 16 else socket.AF_INET, raw)


def _decode_transport(number: int, ts: float, length: int, src: str, dst: str, proto: int, body: bytes) -> Packet:
    if proto in (6, 17) and len(body) >= 4:
        sport, dport = struct.unpack("!HH", body[:4])
        info = ""
        if proto == 6 and len(body) >= 14:
            flags = body[13]
            info = " ".join(name for bit, name in ((0x02, "SYN"), (0x10, "ACK"), (0x01, "FIN"), (0x04, "RST")) if flags & bit)
        service = SERVICES.get(dport) or SERVICES.get(sport)
        return Packet(number, ts, length, src, dst, service or IP_PROTO_NAMES[proto], f"{sport} -> {dport}", info)
    if proto in (1, 58) and body:
        return Packet(number, ts, length, src, dst, IP_PROTO_NAMES[proto], info=f"type {body[0]}")
    return Packet(number, ts, length, src, dst, IP_PROTO_NAMES.get(proto, f"IP proto {proto}"))


def _decode_ip(payload: bytes, number: int, ts: float, length: int, ethertype: int) -> Packet | None:
    if ethertype == ETH_IPV4 and len(payload) >= 20:
        ihl = (payload[0] & 0x0F) * 4
        proto, src, dst, body = payload[9], payload[12:16], payload[16:20], payload[ihl:]
    elif ethertype == ETH_IPV6 and len(payload) >= 40:
        proto, src, dst, body = payload[6], payload[8:24], payload[24:40], payload[40:]
    else:
        return None
    return _decode_transport(number, ts, length, _ip_text(src), _ip_text(dst), proto, body)


def _decode_frame(data: bytes, linktype: int, number: int, ts: float, length: int) -> Packet | None:
    if linktype == LINKTYPE_ETHERNET and len(data) >= 14:
        ethertype = struct.unpack("!H", data[12:14])[0]
        payload = data[14:]
        if ethertype == ETH_VLAN and len(payload) >= 4:
            ethertype = struct.unpack("!H", payload[2:4])[0]
            payload = payload[4:]
        if ethertype == ETH_ARP and len(payload) >= 28:
            return Packet(number, ts, length, socket.inet_ntoa(payload[14:18]), socket.inet_ntoa(payload[24:28]), "ARP")
        packet = _decode_ip(payload, number, ts, length, ethertype)
        if packet is None:
            mac_src = ":".join(f"{b:02x}" for b in data[6:12])
            mac_dst = ":".join(f"{b:02x}" for b in data[0:6])
            return Packet(number, ts, length, mac_src, mac_dst, f"EtherType 0x{ethertype:04x}")
        return packet
    if linktype == LINKTYPE_RAW and data:
        return _decode_ip(data, number, ts, length, ETH_IPV4 if data[0] >> 4 == 4 else ETH_IPV6)
    if linktype == LINKTYPE_LINUX_SLL and len(data) >= 16:
        return _decode_ip(data[16:], number, ts, length, struct.unpack("!H", data[14:16])[0])
    if linktype == LINKTYPE_LINUX_SLL2 and len(data) >= 20:
        return _decode_ip(data[20:], number, ts, length, struct.unpack("!H", data[0:2])[0])
    return None


def _classic(f: Any) -> Iterator[Packet]:
    head = f.read(24)
    magic = head[:4]
    if magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    elif magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    else:
        raise ValueError("not a libpcap file")
    nanos = magic in (b"\xa1\xb2\x3c\x4d", b"\x4d\x3c\xb2\xa1")
    linktype = struct.unpack(endian + "I", head[20:24])[0]
    number = 0
    while True:
        rec = f.read(16)
        if len(rec) < 16:
            return
        sec, frac, incl, orig = struct.unpack(endian + "IIII", rec)
        data = f.read(incl)
        if len(data) < incl:
            return
        number += 1
        packet = _decode_frame(data, linktype, number, sec + frac / (1e9 if nanos else 1e6), orig)
        if packet is not None:
            yield packet


def _pcapng(f: Any, first: bytes) -> Iterator[Packet]:
    """pcapng is a sequence of blocks: type, total length, body, total length again."""
    endian = "<"
    interfaces: list[tuple[int, float]] = []  # per interface: (linktype, seconds per timestamp unit)
    number = 0
    header = first
    while True:
        if header[:4] == PCAPNG_SHB:  # section header: its byte-order magic sets the endianness
            bom = f.read(4)
            endian = "<" if bom == PCAPNG_BOM else ">"
            total = struct.unpack(endian + "I", header[4:8])[0]
            if total < 16 or len(f.read(total - 12)) < total - 12:
                return
            interfaces = []
        else:
            btype, total = struct.unpack(endian + "II", header)
            if total < 12:
                return
            body = f.read(total - 12)
            if len(body) < total - 12:
                return
            if btype == 0x00000001 and len(body) >= 8:  # interface description
                linktype = struct.unpack(endian + "H", body[:2])[0]
                resolution = 1e-6
                pos = 8
                while pos + 4 <= len(body):
                    code, olen = struct.unpack(endian + "HH", body[pos : pos + 4])
                    if code == 0:
                        break
                    if code == 9 and olen >= 1:  # if_tsresol
                        v = body[pos + 4]
                        resolution = 2 ** -(v & 0x7F) if v & 0x80 else 10 ** -v
                    pos += 4 + olen + (-olen % 4)
                interfaces.append((linktype, resolution))
            elif btype == 0x00000006 and len(body) >= 20:  # enhanced packet block
                iface, ts_hi, ts_lo, cap_len, orig_len = struct.unpack(endian + "IIIII", body[:20])
                if iface < len(interfaces):
                    linktype, unit = interfaces[iface]
                    number += 1
                    ts = ((ts_hi << 32) | ts_lo) * unit
                    packet = _decode_frame(body[20 : 20 + cap_len], linktype, number, ts, orig_len)
                    if packet is not None:
                        yield packet
            elif btype == 0x00000003 and len(body) >= 4 and interfaces:  # simple packet block, no timestamp
                number += 1
                orig_len = struct.unpack(endian + "I", body[:4])[0]
                packet = _decode_frame(body[4:], interfaces[0][0], number, 0.0, orig_len)
                if packet is not None:
                    yield packet
            f.read(4)  # trailing block length
        header = f.read(8)
        if len(header) < 8:
            return


def read_packets(path: Path) -> Iterator[Packet]:
    with path.open("rb") as f:
        first = f.read(8)
        if len(first) < 8:
            return
        if first[:4] == PCAPNG_SHB:
            yield from _pcapng(f, first)
            return
        f.seek(0)
        yield from _classic(f)


def summarize(path: Path, max_packets: int = 500_000) -> Summary:
    s = Summary()
    for p in read_packets(path):
        s.packets += 1
        s.bytes += p.length
        s.first = p.time if s.first is None else min(s.first, p.time)
        s.last = p.time if s.last is None else max(s.last, p.time)
        s.protocols[p.protocol] += 1
        s.talkers[p.src] += 1
        s.talkers[p.dst] += 1
        if s.packets >= max_packets:
            s.truncated = True
            break
    return s
