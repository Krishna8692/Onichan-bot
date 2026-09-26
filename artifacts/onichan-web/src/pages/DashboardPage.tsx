import { useQuery } from '@tanstack/react-query';
import { LayoutDashboard, Zap, CreditCard, Wallet, Users, Activity } from 'lucide-react';
import { Link } from 'wouter';
import { getStats } from '@/lib/api';
import { useAuth } from '@/hooks/use-auth';

function StatCard({ label, value, icon, color }: { label: string; value: string | number; icon: React.ReactNode; color: string }) {
  return (
    <div className={`rounded-xl border bg-card p-5 flex items-center gap-4`}>
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-sm text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

function QuickLink({ href, label, icon, desc }: { href: string; label: string; icon: string; desc: string }) {
  return (
    <Link href={href}>
      <div className="rounded-xl border bg-card hover:bg-accent/50 p-4 cursor-pointer transition-colors group">
        <div className="text-2xl mb-2">{icon}</div>
        <p className="font-semibold text-sm group-hover:text-purple-600 transition-colors">{label}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    retry: false,
  });

  const s = (stats as any) || {};

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <LayoutDashboard size={24} className="text-purple-600" />
          Dashboard
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Welcome back{user?.first_name ? `, ${user.first_name}` : ''}! Here's your overview.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total Users"
          value={isLoading ? '…' : (s.total_users ?? s.users ?? '—')}
          icon={<Users size={18} className="text-white" />}
          color="bg-purple-600"
        />
        <StatCard
          label="Premium Users"
          value={isLoading ? '…' : (s.premium_users ?? s.premium ?? '—')}
          icon={<Activity size={18} className="text-white" />}
          color="bg-yellow-500"
        />
        <StatCard
          label="Total Hits"
          value={isLoading ? '…' : (s.total_hits ?? s.hits ?? '—')}
          icon={<Zap size={18} className="text-white" />}
          color="bg-green-600"
        />
        <StatCard
          label="Cards Checked"
          value={isLoading ? '…' : (s.cards_checked ?? s.checks ?? '—')}
          icon={<CreditCard size={18} className="text-white" />}
          color="bg-blue-600"
        />
      </div>

      {/* Quick links */}
      <div>
        <h2 className="text-base font-semibold mb-3">Quick Access</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <QuickLink href="/hitters/auto" label="Auto Hitter" icon="⚡" desc="Hit any gateway automatically" />
          <QuickLink href="/hitters/hitck" label="Checkout.com" icon="🛒" desc="Checkout.com gateway" />
          <QuickLink href="/hitters/hitad" label="Adyen" icon="🔵" desc="Adyen payment gateway" />
          <QuickLink href="/hitters/hitmpgs" label="MPGS" icon="🟠" desc="Mastercard gateway" />
          <QuickLink href="/hitters/hitwhop" label="Whop" icon="🟣" desc="Whop checkout" />
          <QuickLink href="/hitters/hitpad" label="Paddle" icon="🏓" desc="Paddle Billing" />
          <QuickLink href="/hitters/hitep" label="Epoch" icon="🔴" desc="Epoch payments" />
          <QuickLink href="/hitters/jio" label="Jio" icon="📱" desc="Jio recharge/payment" />
          <QuickLink href="/tools/gen" label="Generator" icon="🎲" desc="Generate CC numbers" />
          <QuickLink href="/tools/fake" label="Fake ID" icon="🎭" desc="Generate fake identity" />
          <QuickLink href="/tools/iban" label="IBAN" icon="🏦" desc="Generate IBAN numbers" />
          <QuickLink href="/tools/clean" label="CC Cleaner" icon="🧹" desc="Clean & sort cards" />
        </div>
      </div>

      {/* Status badges */}
      <div className="rounded-xl border bg-card p-4">
        <h2 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wide">System Status</h2>
        <div className="flex flex-wrap gap-2">
          {['Checkout.com', 'Adyen', 'MPGS', 'Whop', 'Paddle', 'Epoch', 'Jio'].map(gw => (
            <span key={gw} className="inline-flex items-center gap-1 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 px-2 py-1 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              {gw}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
