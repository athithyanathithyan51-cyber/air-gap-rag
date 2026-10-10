"""Ed25519 signing key, stored encrypted at rest.

The private key is serialised as PKCS#8 encrypted with the admin passphrase
(cryptography's BestAvailableEncryption). The public key is exported as PEM
for auditors.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

log = logging.getLogger("airgap.attestation")

PRIVATE_FILE = "attestation.key"
PUBLIC_FILE = "attestation.pub"
DEV_PASSPHRASE_FILE = "dev-passphrase.txt"  # noqa: S105 - a file name, not a secret


class AttestationKeyError(RuntimeError):
    pass


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def resolve_passphrase(explicit: str | None, passphrase_file: Path | None, keys_dir: Path, environment: str) -> bytes:
    if explicit:
        return explicit.encode()
    if passphrase_file is not None:
        return passphrase_file.read_text(encoding="utf-8").strip().encode()
    if environment in ("development", "test"):
        dev = keys_dir / DEV_PASSPHRASE_FILE
        if not dev.exists():
            _write_private(dev, secrets.token_urlsafe(32).encode())
            log.warning("dev_passphrase_generated", extra={"path": str(dev)})
        return dev.read_bytes().strip()
    raise AttestationKeyError("attestation passphrase not configured (AIRGAP_ATTESTATION_PASSPHRASE[_FILE])")


def load_or_create(keys_dir: Path, passphrase: bytes) -> Ed25519PrivateKey:
    priv_path = keys_dir / PRIVATE_FILE
    pub_path = keys_dir / PUBLIC_FILE
    if priv_path.exists():
        try:
            key = serialization.load_pem_private_key(priv_path.read_bytes(), password=passphrase)
        except (ValueError, TypeError) as exc:
            raise AttestationKeyError("cannot decrypt attestation key: wrong passphrase or corrupt key file") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise AttestationKeyError("attestation key is not Ed25519")
        return key
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(passphrase),
    )
    _write_private(priv_path, pem)
    pub_path.write_bytes(public_pem(key.public_key()))
    log.info("attestation_key_created", extra={"public_key": str(pub_path)})
    return key


def public_pem(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
