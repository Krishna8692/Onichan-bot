"""
Centralized crypto chain configuration shared by the bot, the wallet API,
and the front-end (via JSON dump).

Single source of truth for:
  - human-readable chain labels
  - address-format regex per chain
  - block-explorer URL templates (tx + address)
  - public RPC endpoints (used by the on-chain broadcaster)
  - native gas symbol & decimals
  - asset → eligible-chain mapping

Also provides:
  - parse_recipient(raw, asset=None, chain_hint=None) → classification dict
  - asset_compatible_chains(asset)
  - chain_supports_asset(chain, asset)
  - explorer_tx_url(chain, tx_hash) / explorer_addr_url(chain, addr)
  - to_frontend_json() — JSON-encodable dict for the Withdraw UI
"""
from __future__ import annotations

import json
import re
from typing import Optional


# --- Chain registry ----------------------------------------------------------

_HEX_ADDR_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_TRON_ADDR_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
_SOL_ADDR_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_TON_ADDR_RE = re.compile(r"^(?:[EU]Q[A-Za-z0-9_-]{46}|0:[a-fA-F0-9]{64})$")
_BTC_ADDR_RE = re.compile(
    r"^(?:bc1[02-9ac-hj-np-z]{6,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$"
)


CHAINS: dict[str, dict] = {
    "ethereum": {
        "label": "Ethereum (ERC-20)",
        "address_re": _HEX_ADDR_RE,
        "explorer_tx": "https://etherscan.io/tx/{tx}",
        "explorer_addr": "https://etherscan.io/address/{addr}",
        "rpc": ["https://eth.llamarpc.com", "https://ethereum-rpc.publicnode.com"],
        "chain_id": 1,
        "native_symbol": "ETH",
        "native_decimals": 18,
        "is_evm": True,
    },
    "bsc": {
        "label": "BNB Smart Chain (BEP-20)",
        "address_re": _HEX_ADDR_RE,
        "explorer_tx": "https://bscscan.com/tx/{tx}",
        "explorer_addr": "https://bscscan.com/address/{addr}",
        "rpc": ["https://bsc-dataseed.binance.org", "https://bsc-rpc.publicnode.com"],
        "chain_id": 56,
        "native_symbol": "BNB",
        "native_decimals": 18,
        "is_evm": True,
    },
    "polygon": {
        "label": "Polygon (PoS)",
        "address_re": _HEX_ADDR_RE,
        "explorer_tx": "https://polygonscan.com/tx/{tx}",
        "explorer_addr": "https://polygonscan.com/address/{addr}",
        "rpc": ["https://polygon-rpc.com", "https://polygon-bor-rpc.publicnode.com"],
        "chain_id": 137,
        "native_symbol": "POL",
        "native_decimals": 18,
        "is_evm": True,
    },
    "arbitrum": {
        "label": "Arbitrum One",
        "address_re": _HEX_ADDR_RE,
        "explorer_tx": "https://arbiscan.io/tx/{tx}",
        "explorer_addr": "https://arbiscan.io/address/{addr}",
        "rpc": ["https://arb1.arbitrum.io/rpc", "https://arbitrum-one-rpc.publicnode.com"],
        "chain_id": 42161,
        "native_symbol": "ETH",
        "native_decimals": 18,
        "is_evm": True,
    },
    "optimism": {
        "label": "Optimism",
        "address_re": _HEX_ADDR_RE,
        "explorer_tx": "https://optimistic.etherscan.io/tx/{tx}",
        "explorer_addr": "https://optimistic.etherscan.io/address/{addr}",
        "rpc": ["https://mainnet.optimism.io", "https://optimism-rpc.publicnode.com"],
        "chain_id": 10,
        "native_symbol": "ETH",
        "native_decimals": 18,
        "is_evm": True,
    },
    "avalanche": {
        "label": "Avalanche C-Chain",
        "address_re": _HEX_ADDR_RE,
        "explorer_tx": "https://snowtrace.io/tx/{tx}",
        "explorer_addr": "https://snowtrace.io/address/{addr}",
        "rpc": ["https://api.avax.network/ext/bc/C/rpc", "https://avalanche-c-chain-rpc.publicnode.com"],
        "chain_id": 43114,
        "native_symbol": "AVAX",
        "native_decimals": 18,
        "is_evm": True,
    },
    "tron": {
        "label": "Tron (TRC-20)",
        "address_re": _TRON_ADDR_RE,
        "explorer_tx": "https://tronscan.org/#/transaction/{tx}",
        "explorer_addr": "https://tronscan.org/#/address/{addr}",
        "rpc": ["https://api.trongrid.io"],
        "native_symbol": "TRX",
        "native_decimals": 6,
        "is_evm": False,
    },
    "solana": {
        "label": "Solana",
        "address_re": _SOL_ADDR_RE,
        "explorer_tx": "https://solscan.io/tx/{tx}",
        "explorer_addr": "https://solscan.io/account/{addr}",
        "rpc": ["https://api.mainnet-beta.solana.com"],
        "native_symbol": "SOL",
        "native_decimals": 9,
        "is_evm": False,
    },
    "ton": {
        "label": "TON",
        "address_re": _TON_ADDR_RE,
        "explorer_tx": "https://tonscan.org/tx/{tx}",
        "explorer_addr": "https://tonscan.org/address/{addr}",
        "rpc": ["https://toncenter.com/api/v2"],
        "native_symbol": "TON",
        "native_decimals": 9,
        "is_evm": False,
    },
    "bitcoin": {
        "label": "Bitcoin",
        "address_re": _BTC_ADDR_RE,
        "explorer_tx": "https://blockstream.info/tx/{tx}",
        "explorer_addr": "https://blockstream.info/address/{addr}",
        "rpc": ["https://blockstream.info/api"],
        "native_symbol": "BTC",
        "native_decimals": 8,
        "is_evm": False,
    },
}


# --- Asset registry ---------------------------------------------------------
#
# Each asset maps to one or more chains it can withdraw on.
# For ERC-20-style tokens, the contract address per chain is stored too.

ASSETS: dict[str, dict] = {
    "ETH":  {"display": "Ethereum",  "chains": ["ethereum", "arbitrum", "optimism"], "decimals": 18, "contract": {}},
    "BNB":  {"display": "BNB",       "chains": ["bsc"],       "decimals": 18, "contract": {}},
    "POL":  {"display": "Polygon",   "chains": ["polygon"],   "decimals": 18, "contract": {}},
    "MATIC":{"display": "Polygon",   "chains": ["polygon"],   "decimals": 18, "contract": {}},
    "AVAX": {"display": "Avalanche", "chains": ["avalanche"], "decimals": 18, "contract": {}},
    "SOL":  {"display": "Solana",    "chains": ["solana"],    "decimals": 9,  "contract": {}},
    "TON":  {"display": "Toncoin",   "chains": ["ton"],       "decimals": 9,  "contract": {}},
    "BTC":  {"display": "Bitcoin",   "chains": ["bitcoin"],   "decimals": 8,  "contract": {}},
    "TRX":  {"display": "TRON",      "chains": ["tron"],      "decimals": 6,  "contract": {}},

    "USDT_TRC20": {
        "display": "USDT (TRC-20)",
        "chains": ["tron"],
        "decimals": 6,
        "contract": {"tron": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"},
    },
    "USDT_ERC20": {
        "display": "USDT (ERC-20)",
        "chains": ["ethereum"],
        "decimals": 6,
        "contract": {"ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7"},
    },
    "USDT_BEP20": {
        "display": "USDT (BEP-20)",
        "chains": ["bsc"],
        "decimals": 18,
        "contract": {"bsc": "0x55d398326f99059fF775485246999027B3197955"},
    },
    "USDT_TON": {"display": "USDT (TON)", "chains": ["ton"], "decimals": 6, "contract": {}},
    "USDT_SOL": {"display": "USDT (SOL)", "chains": ["solana"], "decimals": 6, "contract": {}},
    "USDC_ERC20": {
        "display": "USDC (ERC-20)",
        "chains": ["ethereum"],
        "decimals": 6,
        "contract": {"ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
    },
    "USDC_SOL": {"display": "USDC (SOL)", "chains": ["solana"], "decimals": 6, "contract": {}},
}


# --- Lookups ----------------------------------------------------------------

def asset_compatible_chains(asset: str) -> list[str]:
    a = (asset or "").upper()
    return list((ASSETS.get(a) or {}).get("chains", []))


def chain_supports_asset(chain: str, asset: str) -> bool:
    return (chain or "").lower() in asset_compatible_chains(asset)


def asset_decimals(asset: str) -> int:
    return int((ASSETS.get((asset or "").upper()) or {}).get("decimals", 18))


def asset_contract(asset: str, chain: str) -> Optional[str]:
    a = ASSETS.get((asset or "").upper()) or {}
    return (a.get("contract") or {}).get((chain or "").lower())


def explorer_tx_url(chain: str, tx_hash: str) -> str:
    c = CHAINS.get((chain or "").lower())
    if not c or not tx_hash:
        return ""
    return c["explorer_tx"].format(tx=tx_hash)


def explorer_addr_url(chain: str, addr: str) -> str:
    c = CHAINS.get((chain or "").lower())
    if not c or not addr:
        return ""
    return c["explorer_addr"].format(addr=addr)


def chain_label(chain: str) -> str:
    return (CHAINS.get((chain or "").lower()) or {}).get("label", chain or "")


def detect_chains_for_address(address: str) -> list[str]:
    """Return the list of chains whose address regex this string matches."""
    if not address:
        return []
    s = address.strip()
    out: list[str] = []
    for name, cfg in CHAINS.items():
        if cfg["address_re"].match(s):
            out.append(name)
    return out


# --- Recipient parser -------------------------------------------------------

_USERNAME_RE = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{2,31}$")
_DIGITS_RE = re.compile(r"^\d{4,20}$")


def parse_recipient(
    raw: str,
    asset: Optional[str] = None,
    chain_hint: Optional[str] = None,
) -> dict:
    """
    Classify a withdraw recipient string into one of:

      {'kind':'tg_id','telegram_id':123}
      {'kind':'tg_username','username':'alice'}
      {'kind':'address','address':'…','chain':'ethereum','candidates':['ethereum',…]}
      {'error':'…'}

    For 'address' results, `chain` is the resolved single chain (when only one
    candidate matches, or `chain_hint` is supplied and valid). `candidates`
    always lists every chain whose address format matches — the UI uses it to
    show a network picker for ambiguous (e.g. EVM) addresses. When `asset` is
    provided, candidates are intersected with `asset_compatible_chains(asset)`
    so picking USDT (TRC-20) and pasting an EVM address yields an error.
    """
    if not raw:
        return {"error": "Recipient is required"}
    s = raw.strip()

    # Numeric → telegram id
    if _DIGITS_RE.match(s):
        return {"kind": "tg_id", "telegram_id": int(s)}

    # @username (or bare username that doesn't look like an address)
    if s.startswith("@"):
        u = s[1:]
        if _USERNAME_RE.match("@" + u):
            return {"kind": "tg_username", "username": u}
        return {"error": f"Invalid Telegram username: {s}"}

    # Try to match as a chain address first; only fall back to bare-username
    # if nothing matches and the string is plausibly a username.
    candidates = detect_chains_for_address(s)

    if asset:
        compat = set(asset_compatible_chains(asset))
        if compat:
            filtered = [c for c in candidates if c in compat]
            if candidates and not filtered:
                return {
                    "error": (
                        f"This address is not valid for {asset}. "
                        f"{asset} only supports: {', '.join(sorted(compat))}."
                    )
                }
            candidates = filtered

    if candidates:
        chain = None
        if chain_hint and chain_hint.lower() in candidates:
            chain = chain_hint.lower()
        elif len(candidates) == 1:
            chain = candidates[0]
        return {
            "kind": "address",
            "address": s,
            "chain": chain,
            "candidates": candidates,
        }

    # Last resort: treat as bare username
    if _USERNAME_RE.match(s):
        return {"kind": "tg_username", "username": s}

    return {"error": "Could not interpret recipient. Use @username, Telegram ID, or a valid wallet address."}


# --- Withdrawal fee estimates -----------------------------------------------
#
# Conservative estimates for network/gas fees per chain.
# Shown to users at withdrawal time so they know what to expect.
# These are static estimates — actual fees fluctuate with network congestion.

WITHDRAWAL_FEES: dict[str, dict] = {
    "ethereum":  {"fee": "0.001",    "symbol": "ETH",  "note": "≈ $2–5 (gas, varies)"},
    "bsc":       {"fee": "0.0005",   "symbol": "BNB",  "note": "≈ $0.15–0.40 (gas)"},
    "polygon":   {"fee": "0.02",     "symbol": "POL",  "note": "≈ $0.01 (gas)"},
    "arbitrum":  {"fee": "0.0003",   "symbol": "ETH",  "note": "≈ $0.50–1 (L2 gas)"},
    "optimism":  {"fee": "0.0003",   "symbol": "ETH",  "note": "≈ $0.50–1 (L2 gas)"},
    "avalanche": {"fee": "0.005",    "symbol": "AVAX", "note": "≈ $0.10 (gas)"},
    "tron":      {"fee": "5",        "symbol": "TRX",  "note": "≈ 5 TRX (≈ $0.60)"},
    "solana":    {"fee": "0.000005", "symbol": "SOL",  "note": "≈ $0.001 (flat)"},
    "ton":       {"fee": "0.05",     "symbol": "TON",  "note": "≈ $0.05–0.10 (flat)"},
    "bitcoin":   {"fee": "0.00003",  "symbol": "BTC",  "note": "≈ $2–5 (varies)"},
}


def withdrawal_fee(chain: str) -> tuple[str, str, str]:
    """
    Return (fee_amount, fee_symbol, fee_note) for the given chain.
    Returns ('', '', '') when the chain is unknown.
    """
    c = WITHDRAWAL_FEES.get((chain or "").lower(), {})
    return c.get("fee", ""), c.get("symbol", ""), c.get("note", "")


# --- Front-end serialization ------------------------------------------------

def to_frontend_json() -> str:
    """Return a JSON literal usable inside the wallet HTML page."""
    chains_out = {}
    for k, v in CHAINS.items():
        chains_out[k] = {
            "label": v["label"],
            "address_re": v["address_re"].pattern,
            "explorer_tx": v["explorer_tx"],
            "explorer_addr": v["explorer_addr"],
            "native_symbol": v["native_symbol"],
            "is_evm": v.get("is_evm", False),
        }
    assets_out = {
        k: {
            "display": v["display"],
            "chains": v["chains"],
            "decimals": v["decimals"],
        }
        for k, v in ASSETS.items()
    }
    fees_out = {
        k: {"fee": v["fee"], "symbol": v["symbol"], "note": v["note"]}
        for k, v in WITHDRAWAL_FEES.items()
    }
    return json.dumps({"chains": chains_out, "assets": assets_out, "fees": fees_out})
