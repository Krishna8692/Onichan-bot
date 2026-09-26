"""
random_wallet.py — Per-user random wallet generator.

Generates independent random keypairs per chain for each Telegram user.
No master mnemonic required: each user's keys are completely isolated.

Supported chains: ETH + all EVM forks, TRON, Bitcoin.

Private keys are encrypted with Fernet (AES-128-CBC + HMAC) before
being written to the database. SESSION_SECRET env var is required;
the module fails closed (returns {}) rather than use a known default.

Usage:
    from modules.random_wallet import get_or_create_addresses
    addrs = get_or_create_addresses(telegram_id)  # {chain: address}
    # Returns {} when SESSION_SECRET is unset or DB is unavailable.
"""
from __future__ import annotations

import base64
import hashlib
import os
import threading
from typing import Optional

# ---------------------------------------------------------------------------
# Encryption helpers — fail closed if SESSION_SECRET is absent
# ---------------------------------------------------------------------------

_FERNET_LOCK = threading.Lock()
_FERNET_INSTANCE = None  # type: ignore[assignment]
_FERNET_UNAVAILABLE = False  # set True once we know it can't be configured


def _get_fernet():
    """
    Return a cached Fernet instance keyed from SESSION_SECRET.
    Raises RuntimeError if SESSION_SECRET is not set or cryptography is missing.
    Never uses a default/fallback secret for custodial private keys.
    """
    global _FERNET_INSTANCE, _FERNET_UNAVAILABLE
    if _FERNET_INSTANCE is not None:
        return _FERNET_INSTANCE
    if _FERNET_UNAVAILABLE:
        raise RuntimeError("SESSION_SECRET not configured — wallet encryption unavailable")

    with _FERNET_LOCK:
        if _FERNET_INSTANCE is not None:
            return _FERNET_INSTANCE

        try:
            from cryptography.fernet import Fernet
        except ImportError:
            _FERNET_UNAVAILABLE = True
            raise RuntimeError("cryptography package not installed — cannot encrypt wallet keys")

        secret = os.environ.get("SESSION_SECRET", "").strip()
        if not secret:
            _FERNET_UNAVAILABLE = True
            raise RuntimeError(
                "SESSION_SECRET env var is required for custodial wallet key encryption. "
                "Set it in Replit Secrets before using the wallet."
            )

        dk = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode("utf-8"),
            b"onichan-wallet-keys-v1",
            iterations=100_000,
            dklen=32,
        )
        key = base64.urlsafe_b64encode(dk)
        _FERNET_INSTANCE = Fernet(key)

    return _FERNET_INSTANCE


def _encrypt(plaintext: str) -> str:
    """Encrypt a private key string. Raises if Fernet is unavailable."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def _decrypt(token: str) -> Optional[str]:
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Chain-specific key generation
# ---------------------------------------------------------------------------

# EVM chains all share one keypair (same address on all of them)
_EVM_CHAINS = frozenset({"ethereum", "bsc", "polygon", "arbitrum", "optimism", "avalanche"})

SUPPORTED_CHAINS = sorted(_EVM_CHAINS) + ["tron", "bitcoin"]

# Sentinel: derivation_index=0 marks a randomly-generated wallet (not HD-derived)
RANDOM_WALLET_INDEX = 0


def _generate_evm() -> tuple[str, str]:
    from eth_account import Account
    acct = Account.create()
    return acct.address, acct.key.hex()


def _generate_tron() -> tuple[str, str]:
    from tronpy.keys import PrivateKey
    pk_bytes = os.urandom(32)
    pk = PrivateKey(pk_bytes)
    return pk.public_key.to_base58check_address(), pk_bytes.hex()


def _generate_bitcoin() -> tuple[str, str]:
    from bip_utils import Bip84, Bip84Coins, Bip44Changes
    seed = os.urandom(64)  # 64 random bytes used directly as BIP84 seed
    acct = (
        Bip84.FromSeed(seed, Bip84Coins.BITCOIN)
        .Purpose()
        .Coin()
        .Account(0)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(0)
    )
    return acct.PublicKey().ToAddress(), acct.PrivateKey().ToWif()


def _generate_keypairs() -> dict[str, tuple[str, str]]:
    """
    Generate fresh random keypairs for all supported chains.
    Returns {chain: (address, plaintext_private_key)}.
    EVM chains share one keypair; TRON and Bitcoin get their own.
    """
    result: dict[str, tuple[str, str]] = {}

    try:
        evm_addr, evm_pk = _generate_evm()
        for chain in _EVM_CHAINS:
            result[chain] = (evm_addr, evm_pk)
    except Exception as e:
        print(f"[RandomWallet] EVM keygen failed: {e}")

    try:
        tron_addr, tron_pk = _generate_tron()
        result["tron"] = (tron_addr, tron_pk)
    except Exception as e:
        print(f"[RandomWallet] TRON keygen failed: {e}")

    try:
        btc_addr, btc_wif = _generate_bitcoin()
        result["bitcoin"] = (btc_addr, btc_wif)
    except Exception as e:
        print(f"[RandomWallet] Bitcoin keygen failed: {e}")

    return result


# ---------------------------------------------------------------------------
# DB persistence — race-safe: always re-read after writes
# ---------------------------------------------------------------------------

def get_or_create_addresses(telegram_id: int) -> dict[str, str]:
    """
    Return {chain: address} for all supported chains.

    First call: generates random keypairs, encrypts private keys, and
    persists to wallet_deposit_addresses (derivation_index=RANDOM_WALLET_INDEX).
    Subsequent calls: reads existing rows — no keygen.

    Only addresses confirmed written to the DB are returned (fail-closed).
    Returns {} when SESSION_SECRET is unset, DB is unavailable, or all
    inserts fail.
    """
    try:
        # Verify encryption is available before generating any keys.
        # Raises RuntimeError if SESSION_SECRET is absent.
        _get_fernet()

        from modules.database import _execute_with_retry, is_db_connected
        if not is_db_connected():
            print("[RandomWallet] DB not connected")
            return {}

        # Load whatever is already in the DB for this user
        rows = _execute_with_retry(
            "SELECT chain, address FROM wallet_deposit_addresses WHERE telegram_id = %s",
            (int(telegram_id),), fetch=True,
        ) or []
        existing = {r["chain"]: r["address"] for r in rows}

        missing = [c for c in SUPPORTED_CHAINS if c not in existing]
        if not missing:
            return {c: existing[c] for c in SUPPORTED_CHAINS if c in existing}

        # Generate keypairs and attempt to persist each one
        keypairs = _generate_keypairs()
        for chain, (address, pk_plain) in keypairs.items():
            if chain in existing:
                continue
            try:
                enc_pk = _encrypt(pk_plain)  # raises if encryption unavailable
            except RuntimeError:
                raise  # propagate — we can't store keys without encryption
            except Exception as e:
                print(f"[RandomWallet] encrypt failed for {chain}: {e}")
                continue

            try:
                _execute_with_retry(
                    """INSERT INTO wallet_deposit_addresses
                           (telegram_id, chain, address, derivation_index, encrypted_private_key)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (telegram_id, chain) DO NOTHING""",
                    (int(telegram_id), chain, address, RANDOM_WALLET_INDEX, enc_pk),
                )
            except Exception as e:
                print(f"[RandomWallet] DB insert failed for {chain}/{telegram_id}: {e}")
                # Don't add to result — re-read below will determine what's durable

        # Always re-read to get the canonical, durable addresses.
        # This handles the ON CONFLICT race: if another request already inserted
        # a different address, we return that one, not the locally generated one.
        rows2 = _execute_with_retry(
            "SELECT chain, address FROM wallet_deposit_addresses WHERE telegram_id = %s",
            (int(telegram_id),), fetch=True,
        ) or []
        canonical = {r["chain"]: r["address"] for r in rows2}
        return {c: canonical[c] for c in SUPPORTED_CHAINS if c in canonical}

    except RuntimeError as e:
        print(f"[RandomWallet] {e}")
        return {}
    except Exception as e:
        print(f"[RandomWallet] get_or_create_addresses error: {e}")
        return {}


def get_decrypted_private_key(telegram_id: int, chain: str) -> Optional[str]:
    """
    Return the decrypted private key for (telegram_id, chain), or None.
    Only works for random-wallet rows (derivation_index == RANDOM_WALLET_INDEX).
    Used by the sweep/withdrawal logic.
    """
    try:
        from modules.database import _execute_with_retry
        row = _execute_with_retry(
            "SELECT encrypted_private_key FROM wallet_deposit_addresses "
            "WHERE telegram_id = %s AND chain = %s AND derivation_index = %s",
            (int(telegram_id), chain.lower(), RANDOM_WALLET_INDEX),
            fetch_one=True,
        )
        if not row or not row.get("encrypted_private_key"):
            return None
        return _decrypt(row["encrypted_private_key"])
    except Exception as e:
        print(f"[RandomWallet] get_decrypted_private_key error: {e}")
        return None
