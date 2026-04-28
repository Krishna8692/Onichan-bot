"""
On-chain broadcaster for custodial wallet withdrawals.

Signs and broadcasts withdrawal transactions for the chains where the bot has
an HD-derived hot wallet. The hot wallet is reserved at derivation index 0
(see hd_wallet.py).

Result tuple from `broadcast(...)`:
  (tx_hash, error)
  - tx_hash: non-empty string on successful broadcast
  - error: one of
      None                       → success
      'unsupported_asset'        → asset/chain combo not understood
      'unsupported_chain_auto'   → chain has no auto-broadcaster (manual fallback)
      'hd_unavailable'           → HD wallet keys not loaded
      'insufficient_hot_balance' → hot wallet doesn't have funds + gas
      'rpc_error: …'             → RPC failure / signing error
"""
from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Optional

import requests as _req

try:
    from modules import chain_config as cc
    from modules import hd_wallet
except Exception:
    import chain_config as cc  # type: ignore
    import hd_wallet  # type: ignore


HOT_WALLET_INDEX = 0


# ─── EVM ────────────────────────────────────────────────────────────────────

def _evm_rpc(chain: str, method: str, params: list) -> dict:
    cfg = cc.CHAINS[chain]
    last_err = None
    for url in cfg["rpc"]:
        try:
            r = _req.post(
                url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=15,
            )
            data = r.json()
            if "error" in data:
                last_err = data["error"]
                continue
            return data.get("result")
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"RPC failed for {chain}.{method}: {last_err}")


def _evm_get_nonce(chain: str, address: str) -> int:
    res = _evm_rpc(chain, "eth_getTransactionCount", [address, "pending"])
    return int(res, 16)


def _evm_get_gas_price(chain: str) -> int:
    res = _evm_rpc(chain, "eth_gasPrice", [])
    return int(res, 16)


def _evm_get_balance(chain: str, address: str) -> int:
    res = _evm_rpc(chain, "eth_getBalance", [address, "latest"])
    return int(res, 16)


def _evm_estimate_gas(chain: str, tx: dict) -> int:
    try:
        res = _evm_rpc(chain, "eth_estimateGas", [tx])
        return int(int(res, 16) * 1.2)
    except Exception:
        # Sane defaults
        if tx.get("data") and tx["data"] != "0x":
            return 80_000
        return 21_000


def _evm_send_raw(chain: str, raw_hex: str) -> str:
    return _evm_rpc(chain, "eth_sendRawTransaction", [raw_hex])


def _evm_erc20_transfer_data(to_addr: str, amount_smallest: int) -> str:
    """ABI-encode `transfer(address,uint256)`."""
    method = "a9059cbb"
    addr_clean = to_addr.lower().replace("0x", "").rjust(64, "0")
    amt_hex = format(amount_smallest, "x").rjust(64, "0")
    return "0x" + method + addr_clean + amt_hex


def _evm_erc20_balance_of(chain: str, contract: str, owner: str) -> int:
    """eth_call balanceOf(owner)."""
    data = "0x70a08231" + owner.lower().replace("0x", "").rjust(64, "0")
    res = _evm_rpc(chain, "eth_call", [{"to": contract, "data": data}, "latest"])
    if not res or res == "0x":
        return 0
    return int(res, 16)


def get_receipt_status(chain: str, tx_hash: str) -> str:
    """
    Poll a broadcast transaction's receipt.

    Returns one of:
      'success'   — included and not reverted
      'reverted'  — included but reverted (refund the user)
      'pending'   — still in mempool / not yet mined
    """
    if not tx_hash:
        return "pending"
    cfg = CHAINS_CFG = cc.CHAINS.get((chain or "").lower())
    if not cfg:
        return "pending"
    if cfg.get("is_evm"):
        try:
            res = _evm_rpc(chain, "eth_getTransactionReceipt", [tx_hash])
            if not res:
                return "pending"
            status = res.get("status")
            if status is None:
                # Pre-Byzantium / unknown — assume success if mined
                return "success"
            return "success" if int(status, 16) == 1 else "reverted"
        except Exception:
            return "pending"
    if (chain or "").lower() == "tron":
        try:
            from tronpy import Tron  # type: ignore
            client = Tron()
            info = client.get_transaction_info(tx_hash)
            if not info:
                return "pending"
            # Energy/contract-level revert: receipt.result == 'OUT_OF_ENERGY',
            # 'REVERT', 'BAD_JUMP_DESTINATION', etc. SUCCESS only counts as
            # success if there's no contractResult error.
            receipt = info.get("receipt") or {}
            recv_res = (receipt.get("result") or "").upper()
            if recv_res and recv_res not in ("SUCCESS", "OK", ""):
                return "reverted"
            # Top-level result tracks tx-level errors (FAILED, etc.)
            top_res = (info.get("result") or "").upper()
            if top_res == "FAILED":
                return "reverted"
            # If we have any block-level confirmation, treat as success.
            if info.get("blockNumber") or info.get("blockTimeStamp"):
                return "success"
            return "pending"
        except Exception:
            return "pending"
    return "pending"


def _broadcast_evm(
    chain: str,
    asset: str,
    to_address: str,
    amount_decimal: Decimal,
) -> tuple[str, Optional[str]]:
    try:
        from eth_account import Account  # type: ignore
        from eth_account._utils.legacy_transactions import (  # type: ignore
            Transaction, encode_transaction,
        )
    except Exception as e:
        return ("", f"rpc_error: eth_account not available: {e}")

    pk_hex = hd_wallet.get_private_key(chain, HOT_WALLET_INDEX)
    if not pk_hex:
        return ("", "hd_unavailable")
    if not pk_hex.startswith("0x"):
        pk_hex = "0x" + pk_hex
    acct = Account.from_key(pk_hex)
    sender = acct.address

    cfg = cc.CHAINS[chain]
    chain_id = cfg["chain_id"]
    contract = cc.asset_contract(asset, chain)

    # Native vs ERC-20
    if contract:
        decimals = cc.asset_decimals(asset)
        amount_smallest = int(Decimal(amount_decimal) * (Decimal(10) ** decimals))
        # Token-balance precheck: avoid signing a tx that will revert.
        try:
            tok_bal = _evm_erc20_balance_of(chain, contract, sender)
            if tok_bal < amount_smallest:
                return ("", "insufficient_hot_balance")
        except Exception:
            pass  # If RPC for balanceOf fails, fall through; receipt-check covers reverts.
        tx = {
            "from": sender,
            "to": contract,
            "value": "0x0",
            "data": _evm_erc20_transfer_data(to_address, amount_smallest),
        }
    else:
        # Treat as native
        # Native-symbol aliases: ETH for any EVM chain (carryover habit),
        # plus MATIC ⇔ POL on Polygon since both names are still in
        # circulation across user balances and explorers.
        sym = asset.upper()
        native = cfg["native_symbol"].upper()
        polygon_aliases = {"POL", "MATIC"}
        ok = (
            sym == native
            or sym == "ETH"
            or (chain.lower() == "polygon" and sym in polygon_aliases)
        )
        if not ok:
            return ("", "unsupported_asset")
        amount_smallest = int(Decimal(amount_decimal) * (Decimal(10) ** cfg["native_decimals"]))
        tx = {
            "from": sender,
            "to": to_address,
            "value": hex(amount_smallest),
            "data": "0x",
        }

    try:
        gas_price = _evm_get_gas_price(chain)
        gas_limit = _evm_estimate_gas(chain, tx)
        nonce = _evm_get_nonce(chain, sender)
        bal = _evm_get_balance(chain, sender)
        gas_cost = gas_price * gas_limit
        # For native transfers, value+gas must fit; for ERC-20, only gas
        needed = gas_cost + (amount_smallest if not contract else 0)
        if bal < needed:
            return ("", "insufficient_hot_balance")

        signed_tx = Account.sign_transaction(
            {
                "to": tx["to"],
                "value": int(tx["value"], 16) if isinstance(tx["value"], str) else int(tx["value"]),
                "data": tx["data"],
                "gas": gas_limit,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": chain_id,
            },
            pk_hex,
        )
        tx_hash = _evm_send_raw(chain, signed_tx.raw_transaction.hex() if hasattr(signed_tx, "raw_transaction") else signed_tx.rawTransaction.hex())
        if isinstance(tx_hash, str) and not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        return (tx_hash, None)
    except RuntimeError as e:
        return ("", f"rpc_error: {e}")
    except Exception as e:
        return ("", f"rpc_error: {e}")


# ─── Tron ───────────────────────────────────────────────────────────────────

def _broadcast_tron(
    asset: str,
    to_address: str,
    amount_decimal: Decimal,
) -> tuple[str, Optional[str]]:
    try:
        from tronpy import Tron  # type: ignore
        from tronpy.keys import PrivateKey  # type: ignore
    except Exception as e:
        return ("", f"rpc_error: tronpy not available: {e}")

    pk_hex = hd_wallet.get_private_key("tron", HOT_WALLET_INDEX)
    if not pk_hex:
        return ("", "hd_unavailable")
    pk_hex = pk_hex.replace("0x", "")
    try:
        priv = PrivateKey(bytes.fromhex(pk_hex))
        sender = priv.public_key.to_base58check_address()
        client = Tron()
        contract_addr = cc.asset_contract(asset, "tron")
        if contract_addr:
            decimals = cc.asset_decimals(asset)
            amt = int(Decimal(amount_decimal) * (Decimal(10) ** decimals))
            contract = client.get_contract(contract_addr)
            # Token-balance precheck (TRC-20)
            try:
                tok_bal = int(contract.functions.balanceOf(sender) or 0)
                if tok_bal < amt:
                    return ("", "insufficient_hot_balance")
            except Exception:
                pass
            txn = (
                contract.functions.transfer(to_address, amt)
                .with_owner(sender)
                .fee_limit(40_000_000)
                .build()
                .sign(priv)
            )
        else:
            if asset.upper() != "TRX":
                return ("", "unsupported_asset")
            amt = int(Decimal(amount_decimal) * (Decimal(10) ** 6))
            # Pre-check hot wallet balance
            try:
                acct_info = client.get_account(sender)
                bal = int(acct_info.get("balance", 0) or 0)
                if bal < amt + 5_000_000:  # tx fee buffer
                    return ("", "insufficient_hot_balance")
            except Exception:
                pass
            txn = (
                client.trx.transfer(sender, to_address, amt)
                .build()
                .sign(priv)
            )
        result = txn.broadcast()
        # tronpy returns dict; success usually has 'result': True and 'txid'
        if not (result.get("result") is True or result.get("code") in (None, "SUCCESS")):
            return ("", f"rpc_error: {result}")
        tx_hash = txn.txid
        return (tx_hash, None)
    except Exception as e:
        return ("", f"rpc_error: {e}")


# ─── Dispatcher ─────────────────────────────────────────────────────────────

def is_auto_broadcastable(chain: str) -> bool:
    c = (chain or "").lower()
    return c in cc.CHAINS and (cc.CHAINS[c].get("is_evm") or c == "tron")


def broadcast(
    chain: str,
    asset: str,
    to_address: str,
    amount_decimal,
) -> tuple[str, Optional[str]]:
    chain = (chain or "").lower()
    if chain not in cc.CHAINS:
        return ("", "unsupported_chain_auto")
    try:
        amount_decimal = Decimal(str(amount_decimal))
    except Exception:
        return ("", "rpc_error: invalid amount")
    if cc.CHAINS[chain].get("is_evm"):
        return _broadcast_evm(chain, asset, to_address, amount_decimal)
    if chain == "tron":
        return _broadcast_tron(asset, to_address, amount_decimal)
    return ("", "unsupported_chain_auto")


def hot_wallet_address(chain: str) -> Optional[str]:
    return hd_wallet.derive_address(chain, HOT_WALLET_INDEX)
