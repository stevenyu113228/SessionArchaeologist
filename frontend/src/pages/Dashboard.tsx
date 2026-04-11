import { useEffect, useState, useRef, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Upload, Database, Clock, AlertTriangle, FileUp } from 'lucide-react';
import { api } from '../api/client';
import type { SessionListItem } from '../api/types';

export default function Dashboard() {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.sessions.list().then(setSessions).catch(e => setError(e.message));
  }, []);

  const uploadFile = useCallback(async (file: File) => {
    const isZip = file.name.endsWith('.zip');
    const isJsonl = file.name.endsWith('.jsonl');
    if (!isZip && !isJsonl) {
      setError('Please upload a .jsonl or .zip file');
      return;
    }
    setImporting(true);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', file);

      const endpoint = isZip ? '/api/sessions/upload-project' : '/api/sessions/upload';
      const res = await fetch(endpoint, { method: 'POST', body: formData });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`${res.status}: ${body}`);
      }
      const data = await res.json();
      // Auto-navigate to session with autorun
      navigate(`/session/${data.id}?autorun=true`);
    } catch (e: any) {
      setError(e.message);
      setImporting(false);
    }
  }, [navigate]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
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

      {/* Upload */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4 mb-8">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Upload size={16} />
          Import Session
        </h2>
        <div
          onClick={() => !importing && fileInputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-lg p-8 flex flex-col items-center gap-3 cursor-pointer transition-colors ${
            dragOver
              ? 'border-[var(--accent-blue)] bg-[var(--accent-blue)]/10'
              : 'border-[var(--border)] hover:border-[var(--text-muted)]'
          } ${importing ? 'opacity-50 pointer-events-none' : ''}`}
        >
          <FileUp size={32} className="text-[var(--text-muted)]" />
          {importing ? (
            <p className="text-sm text-[var(--text-secondary)]">Importing & starting pipeline...</p>
          ) : (
            <>
              <p className="text-sm text-[var(--text-secondary)]">
                Drop a <span className="mono text-[var(--text-primary)]">.jsonl</span> or{' '}
                <span className="mono text-[var(--text-primary)]">.zip</span> file here, or click to browse
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                .jsonl = single session &nbsp;|&nbsp; .zip = project with subagents (auto-runs full pipeline)
              </p>
            </>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".jsonl,.zip"
          onChange={handleFileSelect}
          className="hidden"
        />
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
            {sessions.filter(s => s.status !== 'subagent_placeholder').map(s => (
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
                  No sessions yet. Upload a .jsonl or .zip file to get started.
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
    extracting: 'bg-[var(--accent-yellow)]/20 text-[var(--accent-yellow)]',
    extracted: 'bg-[var(--accent-yellow)]/20 text-[var(--accent-yellow)]',
    synthesizing: 'bg-[var(--accent-blue)]/20 text-[var(--accent-blue)]',
    synthesized: 'bg-[var(--accent-green)]/20 text-[var(--accent-green)]',
    refining: 'bg-[var(--accent-purple)]/20 text-[var(--accent-purple)]',
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[status] || colors.imported}`}>
      {status}
    </span>
  );
}
