import { useState } from 'react';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

const GATES = [
  { id: 'checkout', label: 'Checkout.com', icon: '💳', needsUrl: true, cvvRequired: true },
  { id: 'adyen',    label: 'Adyen (Full)', icon: '🏦', needsUrl: true, cvvRequired: true },
  { id: 'adyen_ccn',label: 'Adyen CCN',   icon: '🔑', needsUrl: true, cvvRequired: false },
  { id: 'mpgs',     label: 'MPGS',         icon: '🌐', needsUrl: true, cvvRequired: true },
  { id: 'whop',     label: 'Whop',         icon: '🛒', needsUrl: true, cvvRequired: true },
  { id: 'paddle',   label: 'Paddle',       icon: '🚣', needsUrl: true, cvvRequired: true },
  { id: 'epoch',    label: 'Epoch/WNU',    icon: '⏳', needsUrl: true, cvvRequired: true },
  { id: 'jio',      label: 'Jio Recharge', icon: '📱', needsUrl: false, cvvRequired: true,
    extraFields: [{ key: 'phone', label: 'Mobile No.', placeholder: '9876543210' },
                  { key: 'plan',  label: 'Plan ID',    placeholder: '239' }] },
];

interface HitResult {
  success: boolean;
  decline_code?: string;
  error?: string;
  merchant?: string;
  amount?: string;
  response_time?: number;
}

export default function Hitters() {
  const [gate, setGate] = useState(GATES[0]);
  const [url, setUrl] = useState('');
  const [card, setCard] = useState('');
  const [extras, setExtras] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HitResult | null>(null);

  const hit = async () => {
    setLoading(true);
    setResult(null);
    try {
      const body: Record<string, string> = { card, gateway: gate.id };
      if (gate.needsUrl) body.url = url;
      Object.assign(body, extras);
      const r = await fetch(`${BASE}/api/tools/${gate.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      setResult(data);
    } catch (e: any) {
      setResult({ success: false, error: String(e) });
    } finally {
      setLoading(false);
    }
  };

  const statusColor = result?.success
    ? 'text-green-400'
    : result
    ? 'text-red-400'
    : 'text-purple-400';

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Hitters</h1>
        <p className="text-sm text-purple-400 mt-1">Hit a payment gateway with a card</p>
      </div>

      {/* Gate selector */}
      <div className="grid grid-cols-4 gap-2">
        {GATES.map(g => (
          <button
            key={g.id}
            onClick={() => { setGate(g); setResult(null); setUrl(''); setExtras({}); }}
            className={`rounded-lg py-2 px-1 text-xs font-semibold flex flex-col items-center gap-1 transition-all ${
              gate.id === g.id
                ? 'bg-purple-600 text-white shadow-lg shadow-purple-900/50'
                : 'bg-[#1a1a2e] text-purple-300 border border-purple-900/30 hover:border-purple-600'
            }`}
          >
            <span className="text-lg">{g.icon}</span>
            {g.label}
          </button>
        ))}
      </div>

      {/* Inputs */}
      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5 space-y-4">
        {gate.needsUrl && (
          <div>
            <label className="text-xs text-purple-400 uppercase tracking-widest">Checkout URL</label>
            <input
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://pay.gateway.com/..."
              className="mt-1 w-full bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white placeholder-purple-800 focus:outline-none focus:border-purple-500"
            />
          </div>
        )}

        {(gate as any).extraFields?.map((f: any) => (
          <div key={f.key}>
            <label className="text-xs text-purple-400 uppercase tracking-widest">{f.label}</label>
            <input
              value={extras[f.key] ?? ''}
              onChange={e => setExtras(prev => ({ ...prev, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
              className="mt-1 w-full bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white placeholder-purple-800 focus:outline-none focus:border-purple-500"
            />
          </div>
        ))}

        <div>
          <label className="text-xs text-purple-400 uppercase tracking-widest">
            Card {gate.cvvRequired ? '(CC|MM|YY|CVV)' : '(CC|MM|YY)'}
          </label>
          <input
            value={card}
            onChange={e => setCard(e.target.value)}
            placeholder={gate.cvvRequired ? '4111111111111111|12|26|123' : '4111111111111111|12|26'}
            className="mt-1 w-full bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white placeholder-purple-800 focus:outline-none focus:border-purple-500 font-mono"
          />
        </div>

        <button
          onClick={hit}
          disabled={loading || !card}
          className="w-full py-2.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold rounded-lg text-sm transition-all"
        >
          {loading ? '⏳ Hitting…' : `${gate.icon} Hit ${gate.label}`}
        </button>
      </div>

      {/* Result */}
      {result && (
        <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5 space-y-2 font-mono text-sm">
          <p className={`font-bold text-base ${statusColor}`}>
            {result.success ? '✅ Approved' : '❌ Declined'}
          </p>
          {result.decline_code && <p className="text-purple-300">Code: <span className="text-white">{result.decline_code}</span></p>}
          {result.error && <p className="text-purple-300">Error: <span className="text-white">{result.error}</span></p>}
          {result.merchant && <p className="text-purple-300">Merchant: <span className="text-white">{result.merchant}</span></p>}
          {result.amount && <p className="text-purple-300">Amount: <span className="text-white">{result.amount}</span></p>}
          {result.response_time && <p className="text-purple-300">Time: <span className="text-white">{result.response_time}s</span></p>}
        </div>
      )}
    </div>
  );
}
