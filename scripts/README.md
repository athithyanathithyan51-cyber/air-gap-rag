# scripts/

- `capture_traffic.sh`: tcpdump on all interfaces during startup, ingest, 100 queries and shutdown (Phase 7/9).
- `verify_isolation.py`: counts packets to non-loopback destinations in a `.pcap`.
- `capture-windows.ps1`: Windows demo laptop only (admin PowerShell, Wi-Fi off). pktmon capture on all adapters, plus a before/after diff of the physical adapters' statistics. PASS = zero packets on Wi-Fi/Ethernet and no default route. Output goes to `data/captures/`.
- `dev-server-windows.sh`: dev server on the Windows laptop.

The header badge in the app also shows a live counter: external traffic since isolation began, plus the app's sockets to non-local addresses. That counter uses OS interface statistics; the captures are the stronger evidence.

Until these have been run and the capture is saved, every zero-traffic statement is **untested**.
