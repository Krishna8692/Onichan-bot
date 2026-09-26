import { useState } from 'react';
import { useRoute } from 'wouter';
import { Loader2, Copy, Check } from 'lucide-react';
import { genCards, genFake, genIban, cleanCards, pickCards } from '@/lib/api';

// ─── Shared helpers ───────────────────────────────────────────────────────

function useCopy() {
  const [copied, setCopied] = useState(false);
  function copy(text: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }
  return { copied, copy };
}

function CopyButton({ text }: { text: string }) {
  const { copied, copy } = useCopy();
  return (
    <button
      onClick={() => copy(text)}
      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
    >
      {copied ? <><Check size={12} className="text-green-500" /> Copied</> : <><Copy size={12} /> Copy</>}
    </button>
  );
}

function ResultBox({ title, content }: { title: string; content: string }) {
  return (
    <div className="rounded-xl border bg-muted/30 p-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</span>
        <CopyButton text={content} />
      </div>
      <pre className="text-xs font-mono whitespace-pre-wrap break-all max-h-64 overflow-y-auto">{content}</pre>
    </div>
  );
}

// ─── Gen page ──────────────────────────────────────────────────────────────

function GenPage() {
  const [bin, setBin] = useState('');
  const [count, setCount] = useState(10);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ cards: string[]; brand: string } | null>(null);
  const [error, setError] = useState('');

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await genCards(bin.trim(), count);
      setResult(r);
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div className="max-w-lg space-y-5">
      <div>
        <h1 className="text-2xl font-bold">🎲 Card Generator</h1>
        <p className="text-muted-foreground text-sm mt-1">Generate CC numbers from a BIN prefix.</p>
      </div>
      <form onSubmit={handle} className="rounded-xl border bg-card p-5 space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">BIN / Pattern</label>
          <input value={bin} onChange={e => setBin(e.target.value)} placeholder="415920 or 415920|xx|26|xxx" required
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500" />
          <p className="text-xs text-muted-foreground">Use x for random digits. Supports AMEX (15-digit) and standard BINs.</p>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Count</label>
          <input type="number" value={count} onChange={e => setCount(Math.min(500, Math.max(1, +e.target.value)))} min={1} max={500}
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500" />
        </div>
        <button type="submit" disabled={loading || !bin.trim()}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 text-white py-2.5 text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors">
          {loading ? <><Loader2 size={14} className="animate-spin" /> Generating...</> : '🎲 Generate Cards'}
        </button>
      </form>
      {error && <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">⚠️ {error}</div>}
      {result && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-medium">{result.cards.length} cards generated</span>
            <span className="text-muted-foreground">· {result.brand}</span>
          </div>
          <ResultBox title="Generated Cards" content={result.cards.join('\n')} />
        </div>
      )}
    </div>
  );
}

// ─── Fake page ─────────────────────────────────────────────────────────────

const COUNTRIES = [
  { value: 'us', label: '🇺🇸 United States' }, { value: 'uk', label: '🇬🇧 United Kingdom' },
  { value: 'ca', label: '🇨🇦 Canada' }, { value: 'au', label: '🇦🇺 Australia' },
  { value: 'de', label: '🇩🇪 Germany' }, { value: 'fr', label: '🇫🇷 France' },
  { value: 'it', label: '🇮🇹 Italy' }, { value: 'es', label: '🇪🇸 Spain' },
  { value: 'br', label: '🇧🇷 Brazil' }, { value: 'in', label: '🇮🇳 India' },
  { value: 'jp', label: '🇯🇵 Japan' }, { value: 'nl', label: '🇳🇱 Netherlands' },
];

function FakePage() {
  const [country, setCountry] = useState('us');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError(''); setResult(null);
    try { setResult(await genFake(country)); }
    catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div className="max-w-lg space-y-5">
      <div>
        <h1 className="text-2xl font-bold">🎭 Fake Identity Generator</h1>
        <p className="text-muted-foreground text-sm mt-1">Generate realistic fake identities by country.</p>
      </div>
      <form onSubmit={handle} className="rounded-xl border bg-card p-5 space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Country</label>
          <select value={country} onChange={e => setCountry(e.target.value)}
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500">
            {COUNTRIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <button type="submit" disabled={loading}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 text-white py-2.5 text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors">
          {loading ? <><Loader2 size={14} className="animate-spin" /> Generating...</> : '🎭 Generate Identity'}
        </button>
      </form>
      {error && <div className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 border border-red-200 rounded-lg p-3">⚠️ {error}</div>}
      {result && (
        <div className="rounded-xl border bg-card p-5 space-y-3">
          {Object.entries(result).map(([k, v]) => (
            <div key={k} className="flex justify-between items-center text-sm border-b last:border-0 pb-2 last:pb-0">
              <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}</span>
              <div className="flex items-center gap-2">
                <span className="font-medium font-mono text-right max-w-xs truncate">{String(v)}</span>
                <CopyButton text={String(v)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── IBAN page ──────────────────────────────────────────────────────────────

const IBAN_COUNTRIES = [
  { value: '', label: '🎲 Random' },
  { value: 'DE', label: '🇩🇪 Germany' }, { value: 'FR', label: '🇫🇷 France' },
  { value: 'GB', label: '🇬🇧 United Kingdom' }, { value: 'IT', label: '🇮🇹 Italy' },
  { value: 'ES', label: '🇪🇸 Spain' }, { value: 'NL', label: '🇳🇱 Netherlands' },
  { value: 'CH', label: '🇨🇭 Switzerland' }, { value: 'AT', label: '🇦🇹 Austria' },
  { value: 'BE', label: '🇧🇪 Belgium' }, { value: 'PL', label: '🇵🇱 Poland' },
  { value: 'SE', label: '🇸🇪 Sweden' }, { value: 'NO', label: '🇳🇴 Norway' },
  { value: 'DK', label: '🇩🇰 Denmark' }, { value: 'TR', label: '🇹🇷 Turkey' },
  { value: 'SA', label: '🇸🇦 Saudi Arabia' }, { value: 'AE', label: '🇦🇪 UAE' },
];

function IbanPage() {
  const [country, setCountry] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ iban: string; country: string; flag: string; bic: string; bank: string } | null>(null);
  const [error, setError] = useState('');

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError(''); setResult(null);
    try { setResult(await genIban(country || undefined) as any); }
    catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div className="max-w-lg space-y-5">
      <div>
        <h1 className="text-2xl font-bold">🏦 IBAN Generator</h1>
        <p className="text-muted-foreground text-sm mt-1">Generate valid IBAN numbers for 60+ countries.</p>
      </div>
      <form onSubmit={handle} className="rounded-xl border bg-card p-5 space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Country</label>
          <select value={country} onChange={e => setCountry(e.target.value)}
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500">
            {IBAN_COUNTRIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <button type="submit" disabled={loading}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 text-white py-2.5 text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors">
          {loading ? <><Loader2 size={14} className="animate-spin" /> Generating...</> : '🏦 Generate IBAN'}
        </button>
      </form>
      {error && <div className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 border border-red-200 rounded-lg p-3">⚠️ {error}</div>}
      {result && (
        <div className="rounded-xl border bg-card p-5 space-y-3">
          <div className="text-center">
            <div className="text-3xl mb-1">{result.flag}</div>
            <p className="font-semibold">{result.country}</p>
          </div>
          <div className="space-y-2 text-sm">
            {[
              ['IBAN', result.iban],
              ['BIC/SWIFT', result.bic],
              ['Bank', result.bank],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between items-center border-b last:border-0 pb-2 last:pb-0">
                <span className="text-muted-foreground">{k}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono font-medium">{v}</span>
                  <CopyButton text={v} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Clean page ─────────────────────────────────────────────────────────────

function CleanPage() {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ cards: string[]; count: number; dupes: number; stats: Record<string, unknown> } | null>(null);
  const [error, setError] = useState('');

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError(''); setResult(null);
    try { setResult(await cleanCards(text)); }
    catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div className="max-w-xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold">🧹 CC Cleaner</h1>
        <p className="text-muted-foreground text-sm mt-1">Paste messy card data — get clean, sorted, deduplicated cards back.</p>
      </div>
      <form onSubmit={handle} className="rounded-xl border bg-card p-5 space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Paste Cards</label>
          <textarea value={text} onChange={e => setText(e.target.value)} rows={8} required
            placeholder={"4242424242424242|12|28|123\n5412345678901234 12 28 456\n..."}
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none" />
          <p className="text-xs text-muted-foreground">Supports: CC|MM|YY|CVV, CC:MM:YY:CVV, CC/MM/YY/CVV, space-separated</p>
        </div>
        <button type="submit" disabled={loading || !text.trim()}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 text-white py-2.5 text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors">
          {loading ? <><Loader2 size={14} className="animate-spin" /> Cleaning...</> : '🧹 Clean Cards'}
        </button>
      </form>
      {error && <div className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 border border-red-200 rounded-lg p-3">⚠️ {error}</div>}
      {result && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Clean Cards', value: result.count },
              { label: 'Duplicates Removed', value: result.dupes },
            ].map(s => (
              <div key={s.label} className="rounded-lg border bg-card p-3 text-center">
                <p className="text-xl font-bold">{s.value}</p>
                <p className="text-xs text-muted-foreground">{s.label}</p>
              </div>
            ))}
          </div>
          <ResultBox title={`${result.count} Clean Cards`} content={result.cards.join('\n')} />
        </div>
      )}
    </div>
  );
}

// ─── Pick page ──────────────────────────────────────────────────────────────

function PickPage() {
  const [text, setText] = useState('');
  const [count, setCount] = useState(10);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ cards: string[]; count: number; total: number } | null>(null);
  const [error, setError] = useState('');

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError(''); setResult(null);
    try { setResult(await pickCards(text, count)); }
    catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div className="max-w-xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold">🎯 Card Picker</h1>
        <p className="text-muted-foreground text-sm mt-1">Paste a list of cards and pick N random ones.</p>
      </div>
      <form onSubmit={handle} className="rounded-xl border bg-card p-5 space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Paste Cards</label>
          <textarea value={text} onChange={e => setText(e.target.value)} rows={6} required
            placeholder="Paste your card list here..."
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none" />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Pick Count</label>
          <input type="number" value={count} onChange={e => setCount(Math.min(10000, Math.max(1, +e.target.value)))} min={1} max={10000}
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500" />
        </div>
        <button type="submit" disabled={loading || !text.trim()}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 text-white py-2.5 text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors">
          {loading ? <><Loader2 size={14} className="animate-spin" /> Picking...</> : '🎯 Pick Cards'}
        </button>
      </form>
      {error && <div className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 border border-red-200 rounded-lg p-3">⚠️ {error}</div>}
      {result && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">Picked {result.count} of {result.total} cards</p>
          <ResultBox title={`${result.count} Picked Cards`} content={result.cards.join('\n')} />
        </div>
      )}
    </div>
  );
}

// ─── Router ─────────────────────────────────────────────────────────────────

export default function CCToolsPage() {
  const [, genParams] = useRoute('/tools/gen');
  const [, fakeParams] = useRoute('/tools/fake');
  const [, ibanParams] = useRoute('/tools/iban');
  const [, cleanParams] = useRoute('/tools/clean');
  const [, pickParams] = useRoute('/tools/pick');

  if (genParams) return <GenPage />;
  if (fakeParams) return <FakePage />;
  if (ibanParams) return <IbanPage />;
  if (cleanParams) return <CleanPage />;
  if (pickParams) return <PickPage />;
  return <GenPage />;
}
