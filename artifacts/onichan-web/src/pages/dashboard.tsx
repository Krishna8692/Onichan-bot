import { useQuery } from '@tanstack/react-query';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

function StatCard({ label, value, icon }: { label: string; value: string | number; icon: string }) {
  return (
    <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5 flex items-center gap-4">
      <div className="text-3xl">{icon}</div>
      <div>
        <p className="text-xs text-purple-400 uppercase tracking-widest">{label}</p>
        <p className="text-2xl font-bold text-white">{value}</p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: async () => {
      const r = await fetch(`${BASE}/api/stats`);
      if (!r.ok) return null;
      return r.json();
    },
    retry: false,
    refetchInterval: 30_000,
  });

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-sm text-purple-400 mt-1">Bot overview &amp; live stats</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Users" value={stats?.total_users ?? '—'} icon="👥" />
        <StatCard label="Approved" value={stats?.approved_users ?? '—'} icon="✅" />
        <StatCard label="Premium" value={stats?.premium_users ?? '—'} icon="💎" />
        <StatCard label="Hits Today" value={stats?.hits_today ?? '—'} icon="🎯" />
      </div>

      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-purple-300 mb-3 uppercase tracking-widest">FreakyHitter Gates</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { name: 'Checkout.com', cmd: '/hitck', icon: '💳' },
            { name: 'Adyen',        cmd: '/hitad', icon: '🏦' },
            { name: 'Adyen CCN',    cmd: '/hitad1', icon: '🔑' },
            { name: 'MPGS',         cmd: '/hitmpgs', icon: '🌐' },
            { name: 'Whop',         cmd: '/hitwhop', icon: '🛒' },
            { name: 'Paddle',       cmd: '/hitpad', icon: '🚣' },
            { name: 'Epoch',        cmd: '/hitep', icon: '⏳' },
            { name: 'Jio',          cmd: '/jio', icon: '📱' },
          ].map(g => (
            <div key={g.cmd} className="bg-purple-950/30 rounded-lg p-3 flex items-center gap-2">
              <span className="text-xl">{g.icon}</span>
              <div>
                <p className="text-xs font-semibold text-white">{g.name}</p>
                <p className="text-xs text-purple-500 font-mono">{g.cmd}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-purple-300 mb-3 uppercase tracking-widest">CC Tools</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { name: 'IBAN Generator', cmd: '/iban <country>', icon: '🏧' },
            { name: 'Pick Cards',     cmd: '/pick <n>',       icon: '🎲' },
            { name: 'Split List',     cmd: '/split <n>',      icon: '✂️' },
            { name: 'Country Group',  cmd: '/country',        icon: '🌍' },
            { name: 'CC Cleaner',     cmd: '/clean',          icon: '🧹' },
            { name: 'Generator',      cmd: '/gen <bin>',      icon: '⚙️' },
          ].map(t => (
            <div key={t.cmd} className="bg-purple-950/30 rounded-lg p-3 flex items-center gap-2">
              <span className="text-xl">{t.icon}</span>
              <div>
                <p className="text-xs font-semibold text-white">{t.name}</p>
                <p className="text-xs text-purple-500 font-mono">{t.cmd}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
