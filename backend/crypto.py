"""Reversible encryption for secrets stored at rest (e.g. agent API keys).

An API key must be *recoverable* — the agent has to send the real key to the
model provider — so we encrypt it rather than hash it. (A hash like Argon2id is
one-way and could never be used to authenticate.)

Design:
  • A master secret (env ``FAERS_SECRET_KEY``) is stretched into a 32-byte
    encryption key with the **Argon2id** KDF — a memory-hard function that
    makes brute-forcing the master secret expensive.
  • That key drives **Fernet** (AES-128-CBC + HMAC) for authenticated,
    reversible encryption. ``encrypt_secret`` → token, ``decrypt_secret`` →
    plaintext.

The derived key is computed once per process and cached.
"""

from __future__ import annotations

import base64
import functools
import os
import warnings

from cryptography.fernet import Fernet, InvalidToken

# Argon2id landed in cryptography 44; fall back to Scrypt on older versions so
# the app still runs (both are memory-hard KDFs).
try:
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

    _HAVE_ARGON2 = True
except ImportError:  # pragma: no cover - depends on cryptography version
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    _HAVE_ARGON2 = False

# Dev fallback so the app runs out of the box. NEVER rely on this in
# production — set FAERS_SECRET_KEY to a strong, secret value.
_DEV_SECRET = "faers-dev-insecure-secret-change-me"

# Fixed application salt. A per-record salt isn't needed for a single app-wide
# key; the secrecy lives in FAERS_SECRET_KEY. Override with FAERS_SECRET_SALT.
_DEFAULT_SALT = b"faers-agent-kdf-salt-v1"


def _master_secret() -> bytes:
    secret = os.environ.get("FAERS_SECRET_KEY")
    if not secret:
        warnings.warn(
            "FAERS_SECRET_KEY is not set — using an insecure development "
            "secret. Stored API keys are NOT safe. Set FAERS_SECRET_KEY.",
            RuntimeWarning,
            stacklevel=2,
        )
        secret = _DEV_SECRET
    return secret.encode("utf-8")


def _salt() -> bytes:
    override = os.environ.get("FAERS_SECRET_SALT")
    return override.encode("utf-8") if override else _DEFAULT_SALT


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Derive the encryption key once (Argon2id) and build a Fernet instance."""
    salt = _salt()
    if _HAVE_ARGON2:
        kdf = Argon2id(
            salt=salt,
            length=32,
            iterations=3,
            lanes=4,
            memory_cost=64 * 1024,  # 64 MiB
        )
    else:  # pragma: no cover - older cryptography
        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    key = kdf.derive(_master_secret())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Empty input returns ``""`` unchanged."""
    if not plaintext:
        return ""
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt_secret`.

    Returns ``""`` for empty input. Raises :class:`InvalidToken` if the token
    is corrupt or was encrypted under a different master secret.
    """
    if not token:
        return ""
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def is_encrypted(value: str) -> bool:
    """Best-effort check whether ``value`` is one of our Fernet tokens."""
    if not value:
        return False
    try:
        _fernet().decrypt(value.encode("utf-8"))
        return True
    except (InvalidToken, ValueError):
        return False
