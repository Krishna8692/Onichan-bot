import { useQuery } from '@tanstack/react-query';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

export default function Wallet() {
  const { data } = useQuery({
    queryKey: ['wallet-addresses'],
    queryFn: async () => {
      const r = await fetch(`${BASE}/api/wallet/deposit-addresses`);
      if (!r.ok) return null;
      return r.json();
    },
    retry: false,
  });

  const addrs: Record<string, string> = data?.addresses || {};

  return (
    <div className="p-6 space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Wallet</h1>
        <p className="text-sm text-purple-400 mt-1">Custodial crypto deposit addresses</p>
      </div>
      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5 space-y-4">
        {Object.keys(addrs).length === 0 ? (
          <p className="text-sm text-purple-500">No addresses available. Ensure the HD wallet module is configured.</p>
        ) : (
          Object.entries(addrs).map(([chain, addr]) => (
            <div key={chain}>
              <p className="text-xs text-purple-400 uppercase tracking-widest mb-1">{chain}</p>
              <p className="text-sm font-mono text-white break-all bg-black/30 rounded-lg px-3 py-2 select-all">{addr}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
