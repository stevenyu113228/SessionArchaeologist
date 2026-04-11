import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Upload, Database, Clock, AlertTriangle } from 'lucide-react';
import { api } from '../api/client';
import type { SessionListItem } from '../api/types';

export default function Dashboard() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [importPath, setImportPath] = useState('');
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.sessions.list().then(setSessions).catch(e => setError(e.message));
  }, []);

  const handleImport = async () => {
    if (!importPath.trim()) return;
    setImporting(true);
    setError('');
    try {
      await api.sessions.import(importPath.trim());
      const updated = await api.sessions.list();
      setSessions(updated);
      setImportPath('');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setImporting(false);
    }
  };

  const totalTurns = sessions.reduce((s, x) => s + x.total_turns, 0);
  const totalTokens = sessions.reduce((s, x) => s + x.total_tokens_est, 0);

  return (
    <div className="p-6 max-w-5xl">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <StatCard icon={<Database size={18} />} label="Sessions" value={sessions.length} />
        <StatCard icon={<Clock size={18} />} label="Total Turns" value={totalTurns.toLocaleString()} />
        <StatCard icon={<AlertTriangle size={18} />} label="Total Tokens" value={totalTokens.toLocaleString()} />
      </div>

      {/* Import */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4 mb-8">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Upload size={16} />
          Import Session
        </h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={importPath}
            onChange={e => setImportPath(e.target.value)}
            onInput={e => setImportPath((e.target as HTMLInputElement).value)}
            onKeyDown={e => e.key === 'Enter' && handleImport()}
            placeholder="Path to .jsonl file or Claude Code project directory"
            className="flex-1 px-3 py-2 bg-[var(--bg-primary)] border border-[var(--border)] rounded text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)]"
          />
          <button
            onClick={handleImport}
            disabled={importing}
            className="px-4 py-2 bg-[var(--accent-blue)] text-black font-medium rounded text-sm hover:opacity-90 disabled:opacity-50"
          >
            {importing ? 'Importing...' : 'Import'}
          </button>
        </div>
        {error && <p className="text-[var(--accent-red)] text-xs mt-2">{error}</p>}
      </div>

      {/* Session list */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-[var(--text-secondary)] text-left">
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium text-right">Turns</th>
              <th className="px-4 py-3 font-medium text-right">Tokens</th>
              <th className="px-4 py-3 font-medium">Imported</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(s => (
              <tr key={s.id} className="border-b border-[var(--border)] hover:bg-[var(--bg-tertiary)] transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/session/${s.id}`} className="text-[var(--accent-blue)] hover:underline no-underline">
                    {s.name}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={s.status} />
                </td>
                <td className="px-4 py-3 text-right mono">{s.total_turns}</td>
                <td className="px-4 py-3 text-right mono">{s.total_tokens_est.toLocaleString()}</td>
                <td className="px-4 py-3 text-[var(--text-muted)]">
                  {s.imported_at ? new Date(s.imported_at).toLocaleDateString() : '-'}
                </td>
              </tr>
            ))}
            {sessions.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-[var(--text-muted)]">
                  No sessions yet. Import a JSONL file to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4">
      <div className="flex items-center gap-2 text-[var(--text-secondary)] text-xs mb-1">
        {icon} {label}
      </div>
      <div className="text-xl font-bold">{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    imported: 'bg-[var(--text-muted)]/20 text-[var(--text-secondary)]',
    chunked: 'bg-[var(--accent-blue)]/20 text-[var(--accent-blue)]',
    extracted: 'bg-[var(--accent-yellow)]/20 text-[var(--accent-yellow)]',
    synthesized: 'bg-[var(--accent-green)]/20 text-[var(--accent-green)]',
    refining: 'bg-[var(--accent-purple)]/20 text-[var(--accent-purple)]',
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || colors.imported}`}>
      {status}
    </span>
  );
}
