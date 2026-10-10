# Attestation specification (v1)

## What it is
**A tamper-evident record of network-interface state at the moment of each answer.**

It is **not** proof that no packet was ever sent. Packet captures (`scripts/capture_traffic.sh`) are the separate evidence for "no traffic".

## Block schema
Every answer appends one block. Blocks are serialised as canonical JSON: UTF-8, keys sorted, no insignificant whitespace, integers only (no floats). All hashes are SHA-256, hex, lowercase.

| Field | Type | Meaning |
|-------|------|---------|
| `v` | int | Schema version (1) |
| `index` | int | 0-based position in the chain |
| `ts_utc` | string | RFC 3339 UTC timestamp, millisecond precision |
| `counter` | int | Monotonic counter persisted on disk; strictly +1 per block, never reset |
| `query_hash` | hex | SHA-256 of the user's question (NFC-normalised UTF-8) |
| `chunk_hashes` | [hex] | SHA-256 of each retrieved chunk's text, in rank order |
| `answer_hash` | hex | SHA-256 of the final answer text (the refusal text for "I don't know") |
| `outcome` | string | `answered:grounded` or `refused:<reason>` |
| `citations` | [object] | `{doc_id, doc_sha256, page, section}` for each cited source |
| `net` | object | Network snapshot (below) |
| `isolated` | bool | Verdict of the isolation policy for this snapshot |
| `monitor_state` | string | `ISOLATED` or `NOT-ISOLATED` (sticky after a break until the admin acknowledges) |
| `prev_hash` | hex | `block_hash` of block `index-1`; 64 zeros for the genesis block |
| `key_id` | hex | SHA-256 of the raw Ed25519 public key |
| `block_hash` | hex | SHA-256 of the canonical JSON of all fields above |
| `sig` | base64 | Ed25519 signature over the `block_hash` bytes |

### Network snapshot (`net`)
- `interfaces`: one entry for every non-loopback interface, with `{name, up, admin_up, oper, addrs[], kind}`.
  - `admin_up` is the kernel IFF_UP flag. `oper` is the RFC 2863 operational state from `/sys/class/net/<if>/operstate`.
  - `up` = `admin_up` and `oper` not in {down, lowerlayerdown, notpresent}. A network card with its cable unplugged is administratively up, but `oper=down` means it cannot carry traffic, so `up` is false. The policy uses `up`.
  - `kind` is `physical`, `virtual`, or `container-bridge`.
- `default_route_v4` and `default_route_v6`: boolean values.
- `policy`: the isolation policy in force, copied into the block so a verifier needs no extra configuration.

## Isolation policy
**Strict mode (the default).** The snapshot is ISOLATED only if all three hold:
1. No IPv4 or IPv6 default route exists.
2. No `physical` interface is up.
3. Every `virtual` interface that is up appears on the admin allowlist recorded in `policy.allow`. Allowlist entries are interface-name patterns.

**Why there is an allowlist.** Docker creates a host-only bridge, `docker0`, which is up whenever Docker runs. Without an allowlist, the Docker deployment could never be ISOLATED. The default allowlist is `docker0` and `br-*`. Tunnel interfaces (`tun*`, `wg*`, `ppp*`) are never allowed, because they are how traffic would leave.

**Air-gapped LAN mode (opt-in, `AIRGAP_ISOLATION_MODE=lan`).** In this mode, `physical` interfaces whose names are allowlisted may be up, as long as no default route exists. This serves an isolated LAN where users connect from other machines. Every block records the policy mode, so an auditor can see which rule was applied.

## Monitor
The monitor (`attestation/monitor.py`) polls every second (`AIRGAP_MONITOR_INTERVAL_S`). Detection latency on real hardware is **untested**. When an interface not permitted by the policy comes up, it:
1. writes a `break` event to the audit log, and
2. sets `monitor_state=NOT-ISOLATED`.

This state is sticky: every later block carries it until an admin acknowledges. The acknowledgement is itself logged and signed.

## Keys
- One Ed25519 keypair is generated at install time.
- The private key is stored as PKCS#8, encrypted with the admin passphrase using the `cryptography` library's `BestAvailableEncryption`. The passphrase lives in `/etc/airgap/attestation.pass` (root and the app's group only).
- The public key is exported to `keys/attestation.pub` and from **Admin → Public key**. Auditors verify blocks with this public key only.

## Verification (`backend/attestation/verify_chain.py`, standalone, offline)
For each block in order, the verifier checks:
1. canonical recomputation of `block_hash`,
2. the `sig` signature against the public key,
3. that `prev_hash` matches the previous block,
4. that `index` and `counter` are each exactly +1 over the previous block,
5. that `ts_utc` is non-decreasing (a violation is a warning, not a failure: clocks can be changed),
6. that re-evaluating `net` against `policy` gives the stored `isolated` value.

It reports the first broken block and the first NOT-ISOLATED block. Exit codes: 0 = valid and isolated, 1 = broken chain, 2 = valid but contains NOT-ISOLATED blocks.

## Limits (also shown in UI help text)
- **Tamper-evident, not tamper-proof.** Anyone with host access and the private key (or the admin passphrase) can forge an entire new chain.
- **A snapshot shows state at one moment, not all traffic.** An interface can go up and down between polls. Traffic through allowed interfaces is not inspected.
- **Clock manipulation changes timestamps.** The monotonic counter and hash links preserve order, but not wall-clock truth.
- **Docker Desktop on Windows or macOS.** The snapshot describes the Docker VM, not the physical host. Attestation is only meaningful on a native Linux host.
- **Process coverage.** The record says nothing about processes outside this application; that is what OS firewalling (nftables) and packet captures are for.

## Claimed contribution (for the IPR/IIC cell to evaluate)
Attestation is self-contained on one machine:
- no external anchor,
- no cloud key,
- no TEE.

Each RAG answer's citation set and retrieved-chunk hashes are bound to the host's network-isolation state, inside one signed hash-chained record.

Prior art to distinguish from:
- an arXiv egress monitor for LLM agents,
- PyPI `model-witness` (cloud key plus a public blockchain anchor),
- Rebootix zero-egress marketing,
- TEE-based schemes.

This is a design contribution. It is not a granted or confirmed patent. Under Section 3(k) of the Indian Patents Act, any claim must centre on the technical mechanism.
