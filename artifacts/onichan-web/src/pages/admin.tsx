export default function Admin() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Admin</h1>
        <p className="text-sm text-purple-400 mt-1">Bot administration panel</p>
      </div>
      <div className="bg-[#1a1a2e] border border-purple-900/40 rounded-xl p-5">
        <p className="text-sm text-purple-400">
          Admin controls are managed via Telegram bot commands:
        </p>
        <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-2">
          {[
            '/approve', '/ban', '/unban', '/broadcast',
            '/stats', '/pending', '/addadmin', '/removeadmin',
            '/premium', '/rmpremium', '/genkey', '/keys',
          ].map(cmd => (
            <div key={cmd} className="bg-purple-950/30 rounded-lg px-3 py-2 text-xs font-mono text-purple-300">{cmd}</div>
          ))}
        </div>
      </div>
    </div>
  );
}
