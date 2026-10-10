#!/usr/bin/env python3
"""Count packets that involve any non-loopback address in a pcap file.

Pure standard library (no scapy/tshark), so it runs on the air-gapped host.
Reads classic libpcap files (tcpdump -w) with link types EN10MB (1),
RAW (101), LINUX_SLL (113) and LINUX_SLL2 (276, used by `tcpdump -i any`).

A packet is "loopback" only if it is IPv4/IPv6 and BOTH addresses are loopback
(127.0.0.0/8 or ::1). Everything else is reported: IP packets with a
non-loopback source or destination, and non-IP frames (ARP, LLDP, ...) seen on
a non-loopback interface.

Usage:  python verify_isolation.py capture.pcap [--json]
Exit code: 0 if zero non-loopback packets, 1 otherwise, 3 on input error.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import struct
import sys
from collections import Counter
from typing import Any

ETH_IPV4, ETH_IPV6, ETH_VLAN = 0x0800, 0x86DD, 0x8100
LINKTYPE_ETHERNET, LINKTYPE_RAW, LINKTYPE_SLL, LINKTYPE_SLL2 = 1, 101, 113, 276
ARPHRD_LOOPBACK = 772


def _ip_pair(payload: bytes) -> tuple[str, str, int] | None:
    if not payload:
        return None
    version = payload[0] >> 4
    if version == 4 and len(payload) >= 20:
        return (str(ipaddress.IPv4Address(payload[12:16])), str(ipaddress.IPv4Address(payload[16:20])), payload[9])
    if version == 6 and len(payload) >= 40:
        return (str(ipaddress.IPv6Address(payload[8:24])), str(ipaddress.IPv6Address(payload[24:40])), payload[6])
    return None


def _strip_link(linktype: int, frame: bytes) -> tuple[int | None, bytes, bool]:
    """Return (ethertype or None for raw IP, payload, link_is_loopback)."""
    if linktype == LINKTYPE_ETHERNET:
        if len(frame) < 14:
            return None, b"", False
        etype = struct.unpack("!H", frame[12:14])[0]
        off = 14
        while etype == ETH_VLAN and len(frame) >= off + 4:
            etype = struct.unpack("!H", frame[off + 2 : off + 4])[0]
            off += 4
        loop = frame[0:12] == b"\x00" * 12
        return etype, frame[off:], loop
    if linktype == LINKTYPE_RAW:
        return None, frame, False
    if linktype == LINKTYPE_SLL and len(frame) >= 16:
        hatype = struct.unpack("!H", frame[2:4])[0]
        return struct.unpack("!H", frame[14:16])[0], frame[16:], hatype == ARPHRD_LOOPBACK
    if linktype == LINKTYPE_SLL2 and len(frame) >= 20:
        etype = struct.unpack("!H", frame[0:2])[0]
        hatype = struct.unpack("!H", frame[8:10])[0]
        return etype, frame[20:], hatype == ARPHRD_LOOPBACK
    raise ValueError(f"unsupported link type {linktype}")


def analyse(path: str) -> dict[str, Any]:
    with open(path, "rb") as fh:  # noqa: PTH123 - stdlib-only tool
        header = fh.read(24)
        if len(header) < 24:
            raise ValueError("not a pcap file (too short)")
        magic = header[:4]
        if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
            endian = "<"
        elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
            endian = ">"
        elif magic == b"\x0a\x0d\x0d\x0a":
            raise ValueError("pcapng is not supported; capture with `tcpdump -w file.pcap` (classic format)")
        else:
            raise ValueError("not a pcap file (bad magic)")
        linktype = struct.unpack(endian + "I", header[20:24])[0] & 0x0FFFFFFF
        total = loopback = 0
        offenders: Counter[str] = Counter()
        non_ip = 0
        first_ts: float | None = None
        last_ts: float | None = None
        while True:
            rec = fh.read(16)
            if len(rec) < 16:
                break
            ts_sec, ts_frac, incl_len, _orig = struct.unpack(endian + "IIII", rec)
            frame = fh.read(incl_len)
            if len(frame) < incl_len:
                break
            total += 1
            ts = ts_sec + ts_frac / 1e6
            first_ts = ts if first_ts is None else first_ts
            last_ts = ts
            etype, payload, link_loop = _strip_link(linktype, frame)
            if etype not in (None, ETH_IPV4, ETH_IPV6):
                if link_loop:
                    loopback += 1
                else:
                    non_ip += 1
                    offenders[f"non-IP ethertype 0x{etype:04x}"] += 1
                continue
            pair = _ip_pair(payload)
            if pair is None:
                non_ip += 1
                offenders["malformed/unknown IP"] += 1
                continue
            src, dst, proto = pair
            if ipaddress.ip_address(src).is_loopback and ipaddress.ip_address(dst).is_loopback:
                loopback += 1
            else:
                offenders[f"{src} -> {dst} proto {proto}"] += 1
    non_loop = total - loopback
    return {
        "file": path,
        "linktype": linktype,
        "packets_total": total,
        "packets_loopback": loopback,
        "packets_non_loopback": non_loop,
        "non_ip_frames": non_ip,
        "capture_seconds": round((last_ts or 0) - (first_ts or 0), 3),
        "top_non_loopback_flows": offenders.most_common(20),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Count non-loopback packets in a pcap.")
    ap.add_argument("pcap")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        r = analyse(args.pcap)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"file:                 {r['file']}")
        print(f"capture duration:     {r['capture_seconds']} s")
        print(f"packets total:        {r['packets_total']}")
        print(f"packets loopback:     {r['packets_loopback']}")
        print(f"packets NON-loopback: {r['packets_non_loopback']}")
        for flow, n in r["top_non_loopback_flows"]:
            print(f"  {n:6d}  {flow}")
    return 0 if r["packets_non_loopback"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
