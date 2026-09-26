import { Link, useLocation } from 'wouter';

const NAV = [
  { path: '/',           label: 'Dashboard',  icon: '🏠' },
  { path: '/hitters',   label: 'Hitters',    icon: '🎯' },
  { path: '/cc-tools',  label: 'CC Tools',   icon: '🧰' },
  { path: '/generators',label: 'Generators', icon: '⚙️' },
  { path: '/wallet',    label: 'Wallet',     icon: '💰' },
  { path: '/admin',     label: 'Admin',      icon: '🛡️' },
];

export function Sidebar() {
  const [location] = useLocation();

  return (
    <aside className="w-56 shrink-0 bg-[#10102a] border-r border-purple-900/30 flex flex-col min-h-screen">
      {/* Logo */}
      <div className="px-5 py-6 flex items-center gap-3 border-b border-purple-900/30">
        <span className="text-2xl">💜</span>
        <span className="font-bold text-lg text-white tracking-tight">Onichan</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(item => {
          const active = location === item.path || (item.path !== '/' && location.startsWith(item.path));
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                active
                  ? 'bg-purple-600/20 text-purple-300 border border-purple-600/30'
                  : 'text-purple-500 hover:text-purple-300 hover:bg-purple-900/20'
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-purple-900/30">
        <p className="text-xs text-purple-700">Onichan Web Panel</p>
      </div>
    </aside>
  );
}
