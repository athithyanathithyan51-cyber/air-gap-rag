# scripts/

- `capture_traffic.sh`: tcpdump on all interfaces during startup, ingest, 100 queries and shutdown (Phase 7/9).
- `verify_isolation.py`: counts packets to non-loopback destinations in a `.pcap`.

Until these have been run and the capture is saved, every zero-traffic statement is **untested**.
