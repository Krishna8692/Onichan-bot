import { useState } from 'react';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── Card Generator ────────────────────────────────────────────────────────────

function CardGen() {
  const [bin, setBin] = useState('');
  const [count, setCount] = useState('10');
  const [cards, setCards] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/api/tools/gen`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bin, count: parseInt(count) || 10 }),
      });
      const d = await r.json();
      setCards(d.cards || []);
    } catch {
      setCards([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-purple-300 uppercase tracking-widest">⚙️ Card Generator</h2>
      <div className="flex gap-3">
        <input value={bin} onChange={e => setBin(e.target.value)} placeholder="453590|xx|26|xxx"
          className="flex-1 bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-purple-500" />
        <input value={count} onChange={e => setCount(e.target.value)} placeholder="10"
          className="w-20 bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500" />
        <button onClick={generate} disabled={loading || !bin}
          className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold rounded-lg text-sm">
          {loading ? '⏳' : 'Gen'}
        </button>
      </div>
      {cards.length > 0 && (
        <>
          <div className="bg-black/30 rounded-lg p-3 space-y-1 max-h-64 overflow-y-auto">
            {cards.map((c, i) => <p key={i} className="text-xs font-mono text-purple-200 select-all">{c}</p>)}
          </div>
          <button
            onClick={() => navigator.clipboard.writeText(cards.join('\n'))}
            className="text-xs text-purple-400 hover:text-purple-200 transition-colors"
          >
            📋 Copy all
          </button>
        </>
      )}
    </div>
  );
}

// ── Fake Identity ─────────────────────────────────────────────────────────────

function FakeIdentity() {
  const [country, setCountry] = useState('United States');
  const [identity, setIdentity] = useState<Record<string, string> | null>(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/api/tools/fake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ country }),
      });
      const d = await r.json();
      setIdentity(d.identity || null);
    } catch {
      setIdentity(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-purple-300 uppercase tracking-widest">🎭 Fake Identity</h2>
      <div className="flex gap-3">
        <input value={country} onChange={e => setCountry(e.target.value)} placeholder="United States"
          className="flex-1 bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500" />
        <button onClick={generate} disabled={loading}
          className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold rounded-lg text-sm">
          {loading ? '⏳' : 'Generate'}
        </button>
      </div>
      {identity && (
        <div className="bg-black/30 rounded-lg p-4 grid grid-cols-2 gap-2 text-xs">
          {Object.entries(identity).map(([k, v]) => (
            <div key={k}>
              <span className="text-purple-500 capitalize">{k}: </span>
              <span className="text-white">{v}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Generators() {
  return (
    <div className="p-6 space-y-8 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Generators</h1>
        <p className="text-sm text-purple-400 mt-1">Card generator &amp; fake identity</p>
      </div>
      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5">
        <CardGen />
      </div>
      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5">
        <FakeIdentity />
      </div>
    </div>
  );
}
