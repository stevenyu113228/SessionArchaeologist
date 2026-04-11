import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { Pickaxe, LayoutDashboard, FileText } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import SessionView from './pages/SessionView';
import NarrativeView from './pages/NarrativeView';

function App() {
  const location = useLocation();

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <nav className="w-56 shrink-0 border-r border-[var(--border)] bg-[var(--bg-secondary)] flex flex-col">
        <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
          <Pickaxe size={20} className="text-[var(--accent-yellow)]" />
          <span className="font-semibold text-sm">SessionArchaeologist</span>
        </div>
        <div className="p-2 flex flex-col gap-1">
          <NavLink to="/" icon={<LayoutDashboard size={16} />} label="Dashboard" active={location.pathname === '/'} />
          <NavLink to="/" icon={<FileText size={16} />} label="Sessions" active={location.pathname.startsWith('/session')} />
        </div>
        <div className="mt-auto p-3 border-t border-[var(--border)] text-xs text-[var(--text-muted)]">
          v0.1.0 — Phase 2
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/session/:id" element={<SessionView />} />
          <Route path="/session/:id/narrative/:revision" element={<NarrativeView />} />
        </Routes>
      </main>
    </div>
  );
}

function NavLink({ to, icon, label, active }: { to: string; icon: React.ReactNode; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      className={`flex items-center gap-2 px-3 py-2 rounded text-sm no-underline transition-colors ${
        active
          ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]'
      }`}
    >
      {icon}
      {label}
    </Link>
  );
}

export default App;
