import { useState } from 'react';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

// ── IBAN Generator ────────────────────────────────────────────────────────────

function IbanGenerator() {
  const [country, setCountry] = useState('DE');
  const [count, setCount] = useState('5');
  const [ibans, setIbans] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/api/tools/iban`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ country: country.toUpperCase(), count: parseInt(count) || 5 }),
      });
      const d = await r.json();
      setIbans(d.ibans || []);
    } catch {
      setIbans([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-purple-300 uppercase tracking-widest">🏧 IBAN Generator</h2>
      <div className="flex gap-3">
        <input value={country} onChange={e => setCountry(e.target.value.toUpperCase())} maxLength={2}
          placeholder="DE" className="w-20 bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white font-mono uppercase focus:outline-none focus:border-purple-500" />
        <input value={count} onChange={e => setCount(e.target.value)} placeholder="5"
          className="w-24 bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500" />
        <button onClick={generate} disabled={loading}
          className="flex-1 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold rounded-lg text-sm">
          {loading ? '⏳' : 'Generate'}
        </button>
      </div>
      {ibans.length > 0 && (
        <div className="bg-black/30 rounded-lg p-3 space-y-1 max-h-48 overflow-y-auto">
          {ibans.map((ib, i) => <p key={i} className="text-xs font-mono text-purple-200 select-all">{ib}</p>)}
        </div>
      )}
    </div>
  );
}

// ── Card Picker ───────────────────────────────────────────────────────────────

function CardPicker() {
  const [input, setInput] = useState('');
  const [count, setCount] = useState('10');
  const [picked, setPicked] = useState<string[]>([]);

  const pick = () => {
    const lines = input.split('\n').map(l => l.trim()).filter(Boolean);
    const n = Math.min(Math.max(1, parseInt(count) || 10), lines.length);
    const shuffled = [...lines].sort(() => Math.random() - 0.5);
    setPicked(shuffled.slice(0, n));
  };

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-purple-300 uppercase tracking-widest">🎲 Card Picker</h2>
      <textarea value={input} onChange={e => setInput(e.target.value)}
        placeholder="Paste card list here, one per line…"
        rows={5}
        className="w-full bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-xs text-white font-mono resize-none focus:outline-none focus:border-purple-500" />
      <div className="flex gap-3">
        <input value={count} onChange={e => setCount(e.target.value)} placeholder="Count"
          className="w-24 bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500" />
        <button onClick={pick}
          className="flex-1 py-2 bg-purple-600 hover:bg-purple-500 text-white font-semibold rounded-lg text-sm">
          Pick
        </button>
      </div>
      {picked.length > 0 && (
        <div className="bg-black/30 rounded-lg p-3 space-y-1 max-h-48 overflow-y-auto">
          {picked.map((l, i) => <p key={i} className="text-xs font-mono text-purple-200">{l}</p>)}
        </div>
      )}
    </div>
  );
}

// ── CC Cleaner ────────────────────────────────────────────────────────────────

function CardCleaner() {
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const clean = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/api/tools/clean`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: input }),
      });
      const d = await r.json();
      setOutput(d.output || '');
      setStats(d.stats || null);
    } catch {
      setOutput('Error calling API');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-purple-300 uppercase tracking-widest">🧹 CC Cleaner</h2>
      <textarea value={input} onChange={e => setInput(e.target.value)}
        placeholder="Paste raw card data here…"
        rows={6}
        className="w-full bg-black/40 border border-purple-900/40 rounded-lg px-3 py-2 text-xs text-white font-mono resize-none focus:outline-none focus:border-purple-500" />
      <button onClick={clean} disabled={loading || !input}
        className="w-full py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold rounded-lg text-sm">
        {loading ? '⏳ Cleaning…' : '🧹 Clean & Sort'}
      </button>
      {stats && (
        <div className="flex gap-4 text-xs text-purple-400">
          <span>✅ Valid: <b className="text-white">{stats.valid_total}</b></span>
          <span>❌ Invalid: <b className="text-white">{stats.invalid_count}</b></span>
          <span>♻️ Dupes: <b className="text-white">{stats.duplicate_count}</b></span>
        </div>
      )}
      {output && (
        <textarea readOnly value={output} rows={6}
          className="w-full bg-black/30 border border-purple-900/20 rounded-lg px-3 py-2 text-xs text-purple-200 font-mono resize-none" />
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function CcTools() {
  return (
    <div className="p-6 space-y-8 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">CC Tools</h1>
        <p className="text-sm text-purple-400 mt-1">IBAN generator, card picker, cleaner &amp; more</p>
      </div>
      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5">
        <IbanGenerator />
      </div>
      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5">
        <CardPicker />
      </div>
      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5">
        <CardCleaner />
      </div>
    </div>
  );
}
