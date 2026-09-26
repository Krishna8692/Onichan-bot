import { useQuery } from '@tanstack/react-query';
import { ShieldCheck, Users, BarChart3, Activity, ExternalLink } from 'lucide-react';
import { getStats } from '@/lib/api';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

function StatCard({ label, value, icon }: { label: string; value: unknown; icon: string }) {
  return (
    <div className="rounded-xl border bg-card p-5">
      <div className="text-2xl mb-1">{icon}</div>
      <p className="text-2xl font-bold">{value !== undefined ? String(value) : '—'}</p>
      <p className="text-sm text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}

function AdminLink({ href, label, icon, desc }: { href: string; label: string; icon: string; desc: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer"
      className="flex items-start gap-3 rounded-xl border bg-card p-4 hover:bg-accent/50 transition-colors group">
      <span className="text-2xl">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1">
          <p className="font-semibold text-sm group-hover:text-purple-600 transition-colors">{label}</p>
          <ExternalLink size={12} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
      </div>
    </a>
  );
}

export default function AdminPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: getStats,
    retry: false,
    refetchInterval: 30000,
  });

  const s = (stats as any) || {};

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ShieldCheck size={24} className="text-purple-600" />
          Admin Panel
        </h1>
        <p className="text-muted-foreground text-sm mt-1">Overview and management tools for bot administrators.</p>
      </div>

      {/* Stats */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Bot Statistics</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Users" value={isLoading ? '…' : (s.total_users ?? s.users)} icon="👥" />
          <StatCard label="Premium" value={isLoading ? '…' : (s.premium_users ?? s.premium)} icon="⭐" />
          <StatCard label="Banned" value={isLoading ? '…' : (s.banned_users ?? s.banned)} icon="🚫" />
          <StatCard label="Pending" value={isLoading ? '…' : (s.pending_users ?? s.pending)} icon="⏳" />
          <StatCard label="Total Hits" value={isLoading ? '…' : (s.total_hits ?? s.hits)} icon="⚡" />
          <StatCard label="Approved Cards" value={isLoading ? '…' : (s.approved_cards ?? s.approved)} icon="✅" />
          <StatCard label="Admins" value={isLoading ? '…' : (s.admin_count ?? s.admins)} icon="🛡️" />
          <StatCard label="Revenue" value={isLoading ? '…' : (s.total_revenue ? `$${s.total_revenue}` : '—')} icon="💰" />
        </div>
      </div>

      {/* Quick links to admin panel sections */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Admin Tools</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <AdminLink href={`${BASE}/admin/users`} label="User Management" icon="👥" desc="View, approve, ban, and manage users" />
          <AdminLink href={`${BASE}/admin/stats`} label="Bot Statistics" icon="📊" desc="Detailed stats and analytics" />
          <AdminLink href={`${BASE}/admin/keys`} label="Premium Keys" icon="🔑" desc="Generate and manage premium keys" />
          <AdminLink href={`${BASE}/admin/logs`} label="Approved Cards Log" icon="📋" desc="View all approved/live cards" />
          <AdminLink href={`${BASE}/admin/shop`} label="CC Shop" icon="🏪" desc="Manage the CC shop inventory" />
          <AdminLink href={`${BASE}/admin/broadcast`} label="Broadcast" icon="📣" desc="Send messages to all users" />
          <AdminLink href={`${BASE}/admin/autohitter`} label="Auto Hitter" icon="⚡" desc="Bot auto-hitter configuration" />
          <AdminLink href={`${BASE}/admin/wallet`} label="Wallet Management" icon="💳" desc="View and manage user wallets" />
        </div>
      </div>

      {/* Raw stats JSON */}
      <div className="rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Raw Stats</h2>
        {isLoading ? (
          <div className="h-24 bg-muted animate-pulse rounded" />
        ) : (
          <pre className="text-xs font-mono bg-muted p-3 rounded-lg overflow-x-auto max-h-64">
            {JSON.stringify(stats, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
