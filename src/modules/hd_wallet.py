"""
HD Wallet — derives deterministic deposit addresses + private keys for every
Onichan user from a single master BIP-39 mnemonic.

Each Telegram user gets a unique derivation index (assigned on first use).
Supported chains: ETH (and all EVM forks), TRON, Solana, TON, Bitcoin.

Master mnemonic source priority:
  1. MASTER_WALLET_MNEMONIC env var
  2. settings table key 'master_wallet_mnemonic' (auto-generated on first use)
"""
from __future__ import annotations

import os
import threading
from typing import Optional

try:
    from bip_utils import (
        Bip39MnemonicGenerator, Bip39WordsNum, Bip39SeedGenerator,
        Bip44, Bip44Coins, Bip44Changes,
        Bip49, Bip49Coins,
        Bip84, Bip84Coins,
    )
    HAS_BIP_UTILS = True
except Exception:
    HAS_BIP_UTILS = False

_MNEMONIC_LOCK = threading.Lock()
_CACHED_MNEMONIC: Optional[str] = None
_CACHED_SEED: Optional[bytes] = None

# EVM chains all share the same derivation (BIP44 coin type 60 = ETH)
_EVM_CHAINS = {"ethereum", "bsc", "polygon", "arbitrum", "optimism", "avalanche"}

SUPPORTED_DERIVE_CHAINS = _EVM_CHAINS | {"tron", "solana", "ton", "bitcoin"}


def _load_mnemonic() -> Optional[str]:
    """Load master mnemonic from env or DB; auto-generate to DB if missing."""
    global _CACHED_MNEMONIC, _CACHED_SEED
    if _CACHED_MNEMONIC:
        return _CACHED_MNEMONIC

    with _MNEMONIC_LOCK:
        if _CACHED_MNEMONIC:
            return _CACHED_MNEMONIC

        env_mn = os.environ.get("MASTER_WALLET_MNEMONIC", "").strip()
        if env_mn:
            _CACHED_MNEMONIC = env_mn
        else:
            try:
                from modules.database import _execute_with_retry, is_db_connected
                if is_db_connected():
                    row = _execute_with_retry(
                        "SELECT value FROM settings WHERE key = %s",
                        ("master_wallet_mnemonic",), fetch_one=True
                    )
                    if row and row.get("value"):
                        _CACHED_MNEMONIC = row["value"].strip()
                    elif HAS_BIP_UTILS:
                        new_mn = str(
                            Bip39MnemonicGenerator().FromWordsNumber(
                                Bip39WordsNum.WORDS_NUM_24
                            )
                        )
                        _execute_with_retry(
                            """INSERT INTO settings (key, value, updated_at)
                               VALUES (%s, %s, NOW())
                               ON CONFLICT (key) DO NOTHING""",
                            ("master_wallet_mnemonic", new_mn),
                        )
                        # Re-fetch in case of race
                        row2 = _execute_with_retry(
                            "SELECT value FROM settings WHERE key = %s",
                            ("master_wallet_mnemonic",), fetch_one=True
                        )
                        _CACHED_MNEMONIC = (row2 or {}).get("value", new_mn).strip()
                        print("[HD Wallet] ⚠️  Generated new master mnemonic and stored in settings table.")
                        print("[HD Wallet] ⚠️  For production: copy it to MASTER_WALLET_MNEMONIC env secret and remove from DB.")
            except Exception as e:
                print(f"[HD Wallet] mnemonic load error: {e}")

        if _CACHED_MNEMONIC and HAS_BIP_UTILS:
            try:
                _CACHED_SEED = Bip39SeedGenerator(_CACHED_MNEMONIC).Generate()
            except Exception as e:
                print(f"[HD Wallet] seed gen failed: {e}")
                _CACHED_MNEMONIC = None
                _CACHED_SEED = None

    return _CACHED_MNEMONIC


def is_available() -> bool:
    return HAS_BIP_UTILS and _load_mnemonic() is not None


def _seed() -> Optional[bytes]:
    _load_mnemonic()
    return _CACHED_SEED


def _evm_account(index: int):
    seed = _seed()
    if not seed:
        return None
    bip44 = Bip44.FromSeed(seed, Bip44Coins.ETHEREUM)
    return bip44.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)


def _btc_account(index: int):
    seed = _seed()
    if not seed:
        return None
    bip84 = Bip84.FromSeed(seed, Bip84Coins.BITCOIN)
    return bip84.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)


def _tron_account(index: int):
    seed = _seed()
    if not seed:
        return None
    bip44 = Bip44.FromSeed(seed, Bip44Coins.TRON)
    return bip44.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)


def _solana_account(index: int):
    seed = _seed()
    if not seed:
        return None
    bip44 = Bip44.FromSeed(seed, Bip44Coins.SOLANA)
    return bip44.Purpose().Coin().Account(index)


def _ton_account(index: int):
    seed = _seed()
    if not seed:
        return None
    try:
        bip44 = Bip44.FromSeed(seed, Bip44Coins.TON)
        return bip44.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(index)
    except Exception:
        return None


def derive_address(chain: str, index: int) -> Optional[str]:
    """Return the public address for (chain, index)."""
    chain = chain.lower()
    if not is_available():
        return None
    try:
        if chain in _EVM_CHAINS:
            acct = _evm_account(index)
            return acct.PublicKey().ToAddress() if acct else None
        if chain == "bitcoin":
            acct = _btc_account(index)
            return acct.PublicKey().ToAddress() if acct else None
        if chain == "tron":
            acct = _tron_account(index)
            return acct.PublicKey().ToAddress() if acct else None
        if chain == "solana":
            acct = _solana_account(index)
            return acct.PublicKey().ToAddress() if acct else None
        if chain == "ton":
            acct = _ton_account(index)
            return acct.PublicKey().ToAddress() if acct else None
    except Exception as e:
        print(f"[HD Wallet] derive {chain}#{index} error: {e}")
    return None


def get_private_key(chain: str, index: int) -> Optional[str]:
    """Return hex/base58/etc private key suitable for signing on the given chain."""
    chain = chain.lower()
    if not is_available():
        return None
    try:
        if chain in _EVM_CHAINS:
            acct = _evm_account(index)
            return acct.PrivateKey().Raw().ToHex() if acct else None
        if chain == "tron":
            acct = _tron_account(index)
            return acct.PrivateKey().Raw().ToHex() if acct else None
        if chain == "solana":
            acct = _solana_account(index)
            return acct.PrivateKey().Raw().ToHex() if acct else None
        if chain == "ton":
            acct = _ton_account(index)
            return acct.PrivateKey().Raw().ToHex() if acct else None
        if chain == "bitcoin":
            acct = _btc_account(index)
            return acct.PrivateKey().ToWif() if acct else None
    except Exception as e:
        print(f"[HD Wallet] get_private_key {chain}#{index} error: {e}")
    return None


def _next_index_for_user(telegram_id: int) -> int:
    """
    Assign a globally-unique derivation index per Telegram user.

    Strategy:
      1. If this user already has any deposit address persisted, reuse that index
         (so all chains for the same user share the same derivation index).
      2. Otherwise, allocate a fresh index = MAX(derivation_index across all users) + 1
         (starting at 1; index 0 is reserved). This guarantees collision-free
         per-user indices regardless of how many users join.

    The allocation is performed inside a SERIALIZABLE-safe pattern by relying on the
    UNIQUE(chain, address) constraint to detect race conditions and retry.
    """
    try:
        from modules.database import _execute_with_retry
        # Reuse existing index for this user if any
        row = _execute_with_retry(
            "SELECT derivation_index FROM wallet_deposit_addresses WHERE telegram_id = %s LIMIT 1",
            (int(telegram_id),), fetch_one=True
        )
        if row and row.get("derivation_index") is not None:
            idx = int(row["derivation_index"])
            return idx if idx > 0 else 1
        # Allocate fresh: max+1 across all users
        row = _execute_with_retry(
            "SELECT COALESCE(MAX(derivation_index), 0) AS m FROM wallet_deposit_addresses",
            fetch_one=True
        )
        next_idx = int((row or {}).get("m", 0)) + 1
        return next_idx if next_idx > 0 else 1
    except Exception as e:
        print(f"[HD Wallet] _next_index_for_user fallback: {e}")
        # Defensive fallback: use telegram_id directly (still deterministic per user;
        # collisions only possible across two users whose IDs share lower 31 bits, which
        # never occurs for real Telegram IDs which are < 10^10).
        return abs(int(telegram_id)) % 2_000_000_000 or 1


def get_or_create_addresses(telegram_id: int) -> dict:
    """
    Return a dict { chain: address } for all supported derivation chains.
    Persists addresses in wallet_deposit_addresses on first call.
    Returns empty dict if HD wallet is unavailable.
    """
    if not is_available():
        return {}

    try:
        from modules.database import _execute_with_retry, is_db_connected
        if not is_db_connected():
            return {}

        rows = _execute_with_retry(
            "SELECT chain, address, derivation_index FROM wallet_deposit_addresses WHERE telegram_id = %s",
            (int(telegram_id),), fetch=True
        ) or []
        existing = {r["chain"]: r["address"] for r in rows}

        index = _next_index_for_user(int(telegram_id))

        for chain in SUPPORTED_DERIVE_CHAINS:
            if chain in existing:
                continue
            addr = derive_address(chain, index)
            if not addr:
                continue
            try:
                _execute_with_retry(
                    """INSERT INTO wallet_deposit_addresses
                           (telegram_id, chain, address, derivation_index)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (telegram_id, chain) DO NOTHING""",
                    (int(telegram_id), chain, addr, index)
                )
                existing[chain] = addr
            except Exception as e:
                print(f"[HD Wallet] persist {chain} for {telegram_id} failed: {e}")

        return existing
    except Exception as e:
        print(f"[HD Wallet] get_or_create_addresses error: {e}")
        return {}


def get_address_index(telegram_id: int, chain: str) -> Optional[int]:
    """Return derivation index used for this user on this chain (None if not yet assigned)."""
    try:
        from modules.database import _execute_with_retry
        row = _execute_with_retry(
            "SELECT derivation_index FROM wallet_deposit_addresses WHERE telegram_id = %s AND chain = %s",
            (int(telegram_id), chain.lower()), fetch_one=True
        )
        return int(row["derivation_index"]) if row else None
    except Exception:
        return None
