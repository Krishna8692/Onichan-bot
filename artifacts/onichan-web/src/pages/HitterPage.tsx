import { useState } from 'react';
import { useRoute } from 'wouter';
import { Zap, Loader2, CheckCircle2, XCircle, ShieldAlert, AlertCircle } from 'lucide-react';
import { runHitter, type HitResult } from '@/lib/api';

const GATEWAY_META: Record<string, { label: string; icon: string; urlPlaceholder: string; desc: string }> = {
  auto: { label: 'Auto Hitter', icon: '⚡', urlPlaceholder: 'https://example.com/checkout', desc: 'Automatically detects the payment gateway from the URL.' },
  hitck: { label: 'Checkout.com', icon: '🛒', urlPlaceholder: 'https://merchant.com/checkout', desc: 'Hits Checkout.com powered payment pages.' },
  hitad: { label: 'Adyen', icon: '🔵', urlPlaceholder: 'https://shop.com/checkout', desc: 'Hits Adyen Drop-in and API checkout flows.' },
  hitmpgs: { label: 'MPGS', icon: '🟠', urlPlaceholder: 'https://shop.com/pay', desc: 'Hits Mastercard Payment Gateway Services (MPGS).' },
  hitwhop: { label: 'Whop', icon: '🟣', urlPlaceholder: 'https://whop.com/checkout/...', desc: 'Hits Whop.com Stripe-based checkout pages.' },
  hitpad: { label: 'Paddle', icon: '🏓', urlPlaceholder: 'https://buy.paddle.com/product/...', desc: 'Hits Paddle Classic and Paddle Billing checkouts.' },
  hitep: { label: 'Epoch', icon: '🔴', urlPlaceholder: 'https://site.com/join', desc: 'Hits Epoch.com payment forms.' },
  jio: { label: 'Jio', icon: '📱', urlPlaceholder: 'Mobile number (e.g. 9876543210) or Jio URL', desc: 'Hits Jio recharge or payment pages. Use a 10-digit mobile number for recharge.' },
};

function ResultBadge({ result }: { result: HitResult }) {
  const config = {
    live: { icon: <CheckCircle2 size={18} />, label: 'APPROVED', cls: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800' },
    decline: { icon: <XCircle size={18} />, label: 'DECLINED', cls: 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800' },
    '3ds': { icon: <ShieldAlert size={18} />, label: '3DS REQUIRED', cls: 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800' },
    error: { icon: <AlertCircle size={18} />, label: 'ERROR', cls: 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-400 border-gray-200 dark:border-gray-700' },
  }[result.status] || { icon: <AlertCircle size={18} />, label: 'UNKNOWN', cls: 'bg-gray-100 text-gray-700 border-gray-200' };

  return (
    <div className={`rounded-xl border p-5 ${config.cls} space-y-3`}>
      <div className="flex items-center gap-2 text-lg font-bold">
        {config.icon}
        {config.label}
      </div>
      <div className="text-sm space-y-1.5">
        <div className="flex justify-between">
          <span className="opacity-70">Gateway</span>
          <span className="font-medium">{result.gateway}</span>
        </div>
        <div className="flex justify-between">
          <span className="opacity-70">Message</span>
          <span className="font-medium">{result.message}</span>
        </div>
        <div className="flex justify-between">
          <span className="opacity-70">Time</span>
          <span className="font-medium">{result.time_taken}s</span>
        </div>
      </div>
    </div>
  );
}

export default function HitterPage() {
  const [, params] = useRoute('/hitters/:gateway');
  const gateway = (params as any)?.gateway || 'auto';
  const meta = GATEWAY_META[gateway] || GATEWAY_META.auto;

  const [url, setUrl] = useState('');
  const [card, setCard] = useState('');
  const [proxy, setProxy] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<HitResult | null>(null);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim() || !card.trim()) return;

    setLoading(true);
    setResult(null);
    setError('');

    try {
      const res = await runHitter(gateway, { url: url.trim(), card: card.trim(), proxy: proxy.trim() || undefined });
      setResult(res);
    } catch (err: any) {
      setError(err.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <span className="text-2xl">{meta.icon}</span>
          {meta.label}
        </h1>
        <p className="text-muted-foreground text-sm mt-1">{meta.desc}</p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="rounded-xl border bg-card p-5 space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">
            {gateway === 'jio' ? 'Mobile Number or URL' : 'Checkout URL'}
          </label>
          <input
            type="text"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder={meta.urlPlaceholder}
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            required
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Card</label>
          <input
            type="text"
            value={card}
            onChange={e => setCard(e.target.value)}
            placeholder="4242424242424242|12|28|123"
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500"
            required
          />
          <p className="text-xs text-muted-foreground">Format: CC|MM|YY|CVV</p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Proxy <span className="text-muted-foreground">(optional)</span></label>
          <input
            type="text"
            value={proxy}
            onChange={e => setProxy(e.target.value)}
            placeholder="http://user:pass@host:port"
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        <button
          type="submit"
          disabled={loading || !url.trim() || !card.trim()}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-purple-600 text-white py-2.5 text-sm font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? (
            <><Loader2 size={16} className="animate-spin" /> Hitting...</>
          ) : (
            <><Zap size={16} /> Hit {meta.label}</>
          )}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-400">
          ⚠️ {error}
        </div>
      )}

      {/* Result */}
      {result && <ResultBadge result={result} />}
    </div>
  );
}
