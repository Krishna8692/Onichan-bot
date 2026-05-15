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
      'rpc_error: …'             → pre-broadcast RPC/signing failure (safe to refund)
      'rpc_indeterminate: …'     → broadcast was attempted; outcome unknown.
                                   The worker MUST NOT auto-refund — the tx may
                                   have been accepted on-chain. Escalate to the
                                   owner for manual reconciliation.
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
    if (chain or "").lower() == "ton":
        # tx_hash here is the external-message hash returned by sendBocReturnHash.
        # TonCenter's getTransactionsByMessageHash looks up the resulting
        # transaction by incoming-message hash.
        if not tx_hash or tx_hash == "pending_ton":
            # No hash available — keep pending until manual reconciliation.
            return "pending"
        try:
            rpc = cc.CHAINS["ton"]["rpc"][0]
            r = _req.get(
                f"{rpc}/getTransactionsByMessageHash",
                params={"msg_hash": tx_hash, "direction": "in"},
                timeout=15,
            )
            d = r.json()
            if not d.get("ok"):
                return "pending"
            txs = d.get("result", [])
            if not txs:
                return "pending"
            # Transaction was found on-chain — examine compute phase exit code.
            tx = txs[0]
            desc = tx.get("description") or {}
            compute = desc.get("compute_ph") or {}
            exit_code = compute.get("exit_code", 0)
            if exit_code != 0:
                return "reverted"
            return "success"
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
        raw_hex = (
            signed_tx.raw_transaction.hex()
            if hasattr(signed_tx, "raw_transaction")
            else signed_tx.rawTransaction.hex()
        )
    except RuntimeError as e:
        # Failure during pre-broadcast read (gas/nonce/balance) or signing.
        # No tx ever hit the wire → safe to refund.
        return ("", f"rpc_error: {e}")
    except Exception as e:
        return ("", f"rpc_error: {e}")

    # ── BROADCAST BOUNDARY ──
    # From here on, any RPC failure is INDETERMINATE: the tx may have been
    # accepted by one of the upstream nodes even if our request looked like
    # a failure (timeout, dropped TCP, gateway 502, etc.). The caller MUST
    # NOT refund on this branch — only the receipt poller (or owner-driven
    # /confirmwd / /rejectwd) may resolve it.
    try:
        tx_hash = _evm_send_raw(chain, raw_hex)
        if isinstance(tx_hash, str) and not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        return (tx_hash, None)
    except RuntimeError as e:
        return ("", f"rpc_indeterminate: {e}")
    except Exception as e:
        return ("", f"rpc_indeterminate: {e}")


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
    except Exception as e:
        # Failure happened during balance read / build / sign — nothing went
        # to the network. Safe to refund.
        return ("", f"rpc_error: {e}")

    # ── BROADCAST BOUNDARY ──
    # The Tron node may have accepted txn.broadcast() even if we got an
    # exception (e.g. HTTP timeout). Caller must escalate, not refund.
    try:
        result = txn.broadcast()
    except Exception as e:
        return ("", f"rpc_indeterminate: {e}")
    try:
        # tronpy returns dict; success usually has 'result': True and 'txid'
        if not (result.get("result") is True or result.get("code") in (None, "SUCCESS")):
            # The node explicitly rejected — tx_hash exists locally but was
            # not accepted. Treat as indeterminate to be safe (some Tron
            # nodes return a soft-fail while others on the cluster accept).
            return ("", f"rpc_indeterminate: {result}")
        return (txn.txid, None)
    except Exception as e:
        return ("", f"rpc_indeterminate: {e}")


# ─── TON ────────────────────────────────────────────────────────────────────

# Wallet V4R2 contract code (from bip_utils.ton.addr.ton_v4_addr_encoder)
# This matches the addresses derived by bip_utils Bip44Coins.TON
_TON_V4_CODE_B64 = (
    "te6ccgECFAEAAtQAART/APSkE/S88sgLAQIBIAIDAgFIBAUE+PKDCNcYINMf0x/THwL4I7vyZO1E0NMf0x/T"
    "//QE0VFDuvKhUVG68qIF+QFUEGT5EPKj+AAkpMjLH1JAyx9SMMv/UhD0AMntVPgPAdMHIcAAn2xRkyDXSpb"
    "TB9QC+wDoMOAhwAHjACHAAuMAAcADkTDjDQOkyMsfEssfy/8QERITAubQAdDTAyFxsJJfBOAi10nBIJJfBO"
    "AC0x8hghBwbHVnvSKCEGRzdHK9sJJfBeAD+kAwIPpEAcjKB8v/ydDtRNCBAUDXIfQEMFyBAQj0Cm+hMbOS"
    "XwfgBdM/yCWCEHBsdWe6kjgw4w0DghBkc3RyupJfBuMNBgcCASAICQB4AfoA9AQw+CdvIjBQCqEhvvLgUI"
    "IQcGx1Z4MesXCAGFAEywUmzxZY+gIZ9ADLaRfLH1Jgyz8gyYBA+wAGAIpQBIEBCPRZMO1E0IEBQNcgyAHP"
    "FvQAye1UAXKwjiOCEGRzdHKDHrFwgBhQBcsFUAPPFiP6AhPLassfyz/JgED7AJJfA+ICASAKCwBZvSQrb2o"
    "mhAgKBrkPoCGEcNQICEekk30pkQzmkD6f+YN4EoAbeBAUiYcVnzGEAgFYDA0AEbjJftRNDXCx+AA9sp37UT"
    "QgQFA1yH0BDACyMoHy//J0AGBAQj0Cm+hMYAIBIA4PABmtznaiaEAga5Drhf/AABmvHfaiaEAQa5DrhY/AA"
    "G7SB/oA1NQi+QAFyMoHFcv/ydB3dIAYyMsFywIizxZQBfoCFMtrEszMyXP7AMhAFIEBCPRR8qcCAHCBAQjX"
    "GPoA0z/IVCBHgQEI9FHyp4IQbm90ZXB0gBjIywXLAlAGzxZQBPoCFMtqEssfyz/Jc/sAAgBsgQEI1xj6ANM"
    "/MFIkgQEI9Fnyp4IQZHN0cnB0gBjIywXLAlAFzxZQA/oCE8tqyx8Syz/Jc/sAAAr0AMntVA=="
)
_TON_WALLET_ID = 698983191  # subwallet_id for mainnet workchain 0


def _broadcast_ton(
    asset: str,
    to_address: str,
    amount_decimal: Decimal,
) -> tuple[str, Optional[str]]:
    """
    Broadcast a native TON transfer using Wallet V4R2 external message.

    USDT_TON (Jetton transfers) return unsupported_asset until a Jetton
    broadcaster is wired up.
    """
    import base64 as _b64

    try:
        import nacl.signing  # type: ignore
        from pytoniq_core import Cell, begin_cell, Address  # type: ignore
    except Exception as e:
        return ("", f"rpc_error: missing ton deps: {e}")

    if asset.upper() == "USDT_TON":
        return ("", "unsupported_asset")
    if asset.upper() != "TON":
        return ("", "unsupported_asset")

    # ── Keys ──────────────────────────────────────────────────────────────────
    pk_hex = hd_wallet.get_private_key("ton", HOT_WALLET_INDEX)
    if not pk_hex:
        return ("", "hd_unavailable")
    try:
        priv_bytes = bytes.fromhex(pk_hex)[:32]
        signing_key = nacl.signing.SigningKey(priv_bytes)
        pub_bytes = bytes(signing_key.verify_key)
    except Exception as e:
        return ("", f"rpc_error: key error: {e}")

    hot_addr_str = hd_wallet.derive_address("ton", HOT_WALLET_INDEX)
    if not hot_addr_str:
        return ("", "hd_unavailable")

    rpc = cc.CHAINS["ton"]["rpc"][0]

    # ── 1. Account state + balance check ─────────────────────────────────────
    try:
        r = _req.get(
            f"{rpc}/getAddressInformation",
            params={"address": hot_addr_str},
            timeout=15,
        )
        d = r.json()
        if not d.get("ok"):
            return ("", f"rpc_error: getAddressInformation: {d.get('error', d)}")
        result = d["result"]
        acct_state = result.get("state", "uninitialized")
        raw_balance = int(result.get("balance", 0) or 0)
    except Exception as e:
        return ("", f"rpc_error: balance check: {e}")

    amount_nano = int(amount_decimal * Decimal(10**9))
    FEE_NANO = 15_000_000  # 0.015 TON gas buffer
    if raw_balance < amount_nano + FEE_NANO:
        return ("", "insufficient_hot_balance")

    # ── 2. Current seqno ─────────────────────────────────────────────────────
    seqno = 0
    if acct_state == "active":
        try:
            r = _req.post(
                f"{rpc}/runGetMethod",
                json={"address": hot_addr_str, "method": "seqno", "stack": []},
                timeout=15,
            )
            d = r.json()
            if d.get("ok") and d.get("result", {}).get("exit_code") == 0:
                stack = d["result"].get("stack", [])
                if stack:
                    seqno = int(stack[0][1], 16)
        except Exception:
            pass  # seqno = 0 is safe for first-ever tx

    # ── 3. Build internal transfer message ───────────────────────────────────
    try:
        dest = Address(to_address)
    except Exception as e:
        return ("", f"rpc_error: invalid destination address: {e}")

    valid_until = int(time.time()) + 60
    mode = 3  # pay fees separately + ignore action errors

    try:
        internal = (
            begin_cell()
            .store_bit(0)           # int (not ext)
            .store_bit(1)           # ihr_disabled
            .store_bit(0)           # bounce = False (exchange addresses may be uninit)
            .store_bit(0)           # bounced
            .store_uint(0, 2)       # src = addr_none
            .store_address(dest)
            .store_coins(amount_nano)
            .store_uint(0, 1)       # no extra currencies dict
            .store_coins(0)         # ihr_fee
            .store_coins(0)         # fwd_fee
            .store_uint(0, 64)      # created_lt
            .store_uint(0, 32)      # created_at
            .store_uint(0, 1)       # no state_init
            .store_uint(0, 1)       # body inline (empty body)
            .end_cell()
        )

        # Wallet V4 body (subwallet_id | valid_until | seqno | op=0 | mode | ref)
        body = (
            begin_cell()
            .store_uint(_TON_WALLET_ID, 32)
            .store_uint(valid_until, 32)
            .store_uint(seqno, 32)
            .store_uint(0, 8)       # op = 0 (simple send)
            .store_uint(mode, 8)
            .store_ref(internal)
            .end_cell()
        )

        # Sign body hash with Ed25519
        sig = bytes(signing_key.sign(body.hash))[:64]

        # Signed cell: 64-byte sig prefix + body bits + body refs
        signed = (
            begin_cell()
            .store_bytes(sig)
            .store_slice(body.to_slice())
            .end_cell()
        )

        # ── 4. State init (deploy + send in one shot for uninit wallet) ───────
        state_init_cell = None
        if acct_state != "active":
            code_cell = Cell.one_from_boc(_b64.b64decode(_TON_V4_CODE_B64))
            data_cell = (
                begin_cell()
                .store_uint(0, 32)              # seqno = 0
                .store_uint(_TON_WALLET_ID, 32)
                .store_bytes(pub_bytes)
                .store_bit(0)                   # no plugin dict
                .end_cell()
            )
            state_init_cell = (
                begin_cell()
                .store_bit(False)               # no split_depth
                .store_bit(False)               # no special
                .store_maybe_ref(code_cell)
                .store_maybe_ref(data_cell)
                .store_dict(None)               # no library
                .end_cell()
            )

        # ── 5. External message ───────────────────────────────────────────────
        hot_addr = Address(hot_addr_str)
        ext_builder = (
            begin_cell()
            .store_uint(0b10, 2)    # ext_in_msg_info tag
            .store_uint(0, 2)       # src = addr_none
            .store_address(hot_addr)
            .store_coins(0)         # import_fee
        )
        if state_init_cell is not None:
            ext_builder = (
                ext_builder
                .store_bit(1)       # has state_init
                .store_bit(1)       # state_init as ref
                .store_ref(state_init_cell)
            )
        else:
            ext_builder = ext_builder.store_bit(0)  # no state_init

        ext_msg = ext_builder.store_bit(1).store_ref(signed).end_cell()

        boc_b64 = _b64.b64encode(ext_msg.to_boc()).decode()
    except Exception as e:
        return ("", f"rpc_error: message build failed: {e}")

    # ── BROADCAST BOUNDARY ────────────────────────────────────────────────────
    # Once sendBocReturnHash is called the tx may land on-chain even if we
    # get a network error. Caller must NOT auto-refund on rpc_indeterminate.
    try:
        r = _req.post(
            f"{rpc}/sendBocReturnHash",
            json={"boc": boc_b64},
            timeout=30,
        )
        d = r.json()
    except Exception as e:
        return ("", f"rpc_indeterminate: sendBoc network error: {e}")

    if not d.get("ok"):
        err_msg = d.get("error", str(d))
        # Node explicitly rejected before broadcast — safe to surface as rpc_error
        return ("", f"rpc_error: sendBoc rejected: {err_msg}")

    tx_hash = (d.get("result") or {}).get("hash", "")
    return (tx_hash or "pending_ton", None)


# ─── Dispatcher ─────────────────────────────────────────────────────────────

def is_auto_broadcastable(chain: str) -> bool:
    c = (chain or "").lower()
    return c in cc.CHAINS and (
        cc.CHAINS[c].get("is_evm") or c in ("tron", "ton")
    )


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
    if chain == "ton":
        return _broadcast_ton(asset, to_address, amount_decimal)
    return ("", "unsupported_chain_auto")


def hot_wallet_address(chain: str) -> Optional[str]:
    return hd_wallet.derive_address(chain, HOT_WALLET_INDEX)
