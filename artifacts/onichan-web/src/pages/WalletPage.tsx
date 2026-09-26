import { useQuery } from '@tanstack/react-query';
import { Wallet, RefreshCw, Copy, Check, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import { getWalletBalance, getDepositAddresses, getTransactions } from '@/lib/api';

function useCopy() {
  const [copied, setCopied] = useState<string | null>(null);
  function copy(key: string, text: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 2000);
    });
  }
  return { copied, copy };
}

export default function WalletPage() {
  const { copied, copy } = useCopy();

  const { data: balance, isLoading: balLoading, refetch: refetchBal } = useQuery({
    queryKey: ['wallet-balance'],
    queryFn: getWalletBalance,
    retry: false,
  });

  const { data: addresses, isLoading: addrLoading } = useQuery({
    queryKey: ['wallet-addresses'],
    queryFn: getDepositAddresses,
    retry: false,
  });

  const { data: txns, isLoading: txLoading } = useQuery({
    queryKey: ['wallet-txns'],
    queryFn: getTransactions,
    retry: false,
  });

  const bal = (balance as any) || {};
  const addrs = ((addresses as any)?.addresses) || {};
  const txnList = ((txns as any)?.transactions) || [];

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Wallet size={24} className="text-purple-600" />
          Wallet
        </h1>
        <p className="text-muted-foreground text-sm mt-1">Manage your crypto deposits and withdrawals.</p>
      </div>

      {/* Balance card */}
      <div className="rounded-xl border bg-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide">Balance</h2>
          <button onClick={() => refetchBal()} className="text-muted-foreground hover:text-foreground transition-colors">
            <RefreshCw size={14} />
          </button>
        </div>
        {balLoading ? (
          <div className="h-8 w-32 bg-muted animate-pulse rounded" />
        ) : (
          <div className="space-y-2">
            {Object.entries(bal).filter(([k]) => !k.startsWith('_')).map(([coin, amt]) => (
              <div key={coin} className="flex justify-between items-center">
                <span className="text-sm font-medium">{coin.toUpperCase()}</span>
                <span className="font-mono text-lg font-bold">{String(amt)}</span>
              </div>
            ))}
            {Object.keys(bal).length === 0 && (
              <p className="text-muted-foreground text-sm">No balance data available.</p>
            )}
          </div>
        )}
      </div>

      {/* Deposit addresses */}
      <div className="rounded-xl border bg-card p-6">
        <h2 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-4">Deposit Addresses</h2>
        {addrLoading ? (
          <div className="space-y-2">
            {[1,2,3].map(i => <div key={i} className="h-6 bg-muted animate-pulse rounded" />)}
          </div>
        ) : Object.keys(addrs).length === 0 ? (
          <p className="text-muted-foreground text-sm">No deposit addresses configured.</p>
        ) : (
          <div className="space-y-3">
            {Object.entries(addrs).map(([coin, addr]) => (
              <div key={coin} className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground uppercase">{coin}</span>
                  <button onClick={() => copy(coin, String(addr))} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                    {copied === coin ? <><Check size={11} className="text-green-500" /> Copied</> : <><Copy size={11} /> Copy</>}
                  </button>
                </div>
                <code className="text-xs font-mono bg-muted px-3 py-2 rounded-lg w-full block break-all">{String(addr)}</code>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Transactions */}
      <div className="rounded-xl border bg-card p-6">
        <h2 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-4">Recent Transactions</h2>
        {txLoading ? (
          <div className="space-y-3">
            {[1,2,3].map(i => <div key={i} className="h-10 bg-muted animate-pulse rounded" />)}
          </div>
        ) : txnList.length === 0 ? (
          <p className="text-muted-foreground text-sm">No transactions yet.</p>
        ) : (
          <div className="space-y-2">
            {txnList.slice(0, 20).map((tx: any, i: number) => (
              <div key={i} className="flex items-center justify-between text-sm border-b last:border-0 pb-2 last:pb-0">
                <div>
                  <p className="font-medium">{tx.type || 'Transfer'}</p>
                  <p className="text-xs text-muted-foreground">{tx.created_at || tx.date || ''}</p>
                </div>
                <div className="text-right">
                  <p className={`font-mono font-medium ${(tx.amount || 0) > 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {(tx.amount || 0) > 0 ? '+' : ''}{tx.amount} {tx.coin || tx.currency || ''}
                  </p>
                  <p className={`text-xs ${tx.status === 'confirmed' ? 'text-green-500' : 'text-muted-foreground'}`}>{tx.status || ''}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
