# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## Onichan Bot — Custodial Wallet (src/)

The Telegram bot in `src/` runs alongside the workspace. Its custodial wallet:

- **`src/modules/chain_config.py`** — single source of truth for supported chains
  (label, address regex, RPC, explorer URL templates) and assets (native + USDT/USDC
  variants). Exposes `parse_recipient(raw, asset, chain_hint)` that classifies a
  free-form input into Telegram id / username / on-chain address (with `candidates`
  for ambiguous EVM addresses) and `to_frontend_json()` for the wallet UI.
- **`src/modules/onchain_broadcaster.py`** — signs & broadcasts withdrawals.
  EVM (eth_account + JSON-RPC `eth_sendRawTransaction`) handles native + ERC-20
  transfers; Tron (tronpy) handles native TRX + TRC-20. SOL/TON/BTC fall through
  to manual `/confirmwd` until their broadcasters are wired up. The hot wallet
  uses HD derivation index `0`; user deposit addresses start at `1`.
- **Withdraw flow** — `/api/wallet/withdraw` (and `/withdraw` bot command) accept a
  smart `recipient` (username / Telegram id / wallet address). Internal recipients
  are paid atomically inside `_wallet_txn()`. On-chain recipients debit the user,
  insert a `pending` row in `wallet_transactions`, and `_withdrawal_worker` claims
  rows with `UPDATE … FOR UPDATE SKIP LOCKED`, broadcasts, and writes the resulting
  `tx_hash`. Hard failures refund inside the same `_wallet_txn()`; soft failures
  (`insufficient_hot_balance`, `hd_unavailable`) park back to `pending` and ping
  the owner.
- **Explorer links** — every deposit/withdrawal DM and history row renders a 🔍
  link built from `chain_config.explorer_tx_url` / `explorer_addr_url`.

