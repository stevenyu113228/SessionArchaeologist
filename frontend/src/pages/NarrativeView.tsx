import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ChevronLeft, Download, GitCompare, Send } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '../api/client';
import type { NarrativeDetail, NarrativeListItem } from '../api/types';

export default function NarrativeView() {
  const { id, revision } = useParams<{ id: string; revision: string }>();
  const [narrative, setNarrative] = useState<NarrativeDetail | null>(null);
  const [allRevisions, setAllRevisions] = useState<NarrativeListItem[]>([]);
  const [diffText, setDiffText] = useState<string | null>(null);
  const [diffWith, setDiffWith] = useState<number | null>(null);

  useEffect(() => {
    if (!id || !revision) return;
    api.narratives.get(id, parseInt(revision)).then(setNarrative);
    api.narratives.list(id).then(setAllRevisions);
  }, [id, revision]);

  const showDiff = async (otherRev: number) => {
    if (!id || !revision) return;
    const rev = parseInt(revision);
    const { diff } = await api.narratives.diff(id, Math.min(rev, otherRev), Math.max(rev, otherRev));
    setDiffText(diff);
    setDiffWith(otherRev);
  };

  const handleExport = () => {
    if (!narrative) return;
    const blob = new Blob([narrative.content_md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `narrative-rev${narrative.revision}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!narrative) return <div className="p-6 text-[var(--text-muted)]">Loading...</div>;

  return (
    <div className="p-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Link to={`/session/${id}`} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            <ChevronLeft size={20} />
          </Link>
          <div>
            <h1 className="text-xl font-bold">Narrative — Revision {narrative.revision}</h1>
            <p className="text-xs text-[var(--text-muted)]">
              {narrative.synthesis_model} · {narrative.content_md.length.toLocaleString()} chars
              {narrative.created_at && ` · ${new Date(narrative.created_at).toLocaleString()}`}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          {/* Diff selector */}
          {allRevisions.length > 1 && (
            <select
              onChange={e => e.target.value && showDiff(parseInt(e.target.value))}
              value={diffWith ?? ''}
              className="px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border)] rounded text-sm text-[var(--text-primary)]"
            >
              <option value="">Compare with...</option>
              {allRevisions
                .filter(r => r.revision !== narrative.revision)
                .map(r => (
                  <option key={r.revision} value={r.revision}>
                    Rev {r.revision}
                  </option>
                ))}
            </select>
          )}
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-secondary)] border border-[var(--border)] rounded text-sm hover:border-[var(--accent-blue)] transition-colors"
          >
            <Download size={14} /> Export
          </button>
        </div>
      </div>

      {/* Diff view */}
      {diffText !== null && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <GitCompare size={14} />
              Diff: Rev {Math.min(narrative.revision, diffWith!)} → Rev {Math.max(narrative.revision, diffWith!)}
            </h3>
            <button
              onClick={() => { setDiffText(null); setDiffWith(null); }}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              Close
            </button>
          </div>
          <pre className="text-xs overflow-auto max-h-96 mono">
            {diffText.split('\n').map((line, i) => (
              <div
                key={i}
                className={
                  line.startsWith('+') && !line.startsWith('+++')
                    ? 'text-[var(--accent-green)] bg-[var(--accent-green)]/10'
                    : line.startsWith('-') && !line.startsWith('---')
                    ? 'text-[var(--accent-red)] bg-[var(--accent-red)]/10'
                    : line.startsWith('@@')
                    ? 'text-[var(--accent-blue)]'
                    : 'text-[var(--text-secondary)]'
                }
              >
                {line}
              </div>
            ))}
          </pre>
        </div>
      )}

      {/* Narrative content */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-8">
        <article className="prose prose-invert max-w-none text-[var(--text-primary)] [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:mb-4 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:mt-8 [&_h2]:mb-3 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:mt-6 [&_h3]:mb-2 [&_p]:text-sm [&_p]:leading-relaxed [&_p]:mb-3 [&_p]:text-[var(--text-secondary)] [&_code]:bg-[var(--bg-tertiary)] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_pre]:bg-[var(--bg-primary)] [&_pre]:border [&_pre]:border-[var(--border)] [&_pre]:rounded-lg [&_pre]:p-4 [&_pre]:overflow-auto [&_pre]:text-xs [&_li]:text-sm [&_li]:text-[var(--text-secondary)] [&_table]:text-sm [&_th]:text-left [&_th]:p-2 [&_th]:border-b [&_th]:border-[var(--border)] [&_td]:p-2 [&_td]:border-b [&_td]:border-[var(--border)] [&_a]:text-[var(--accent-blue)] [&_strong]:text-[var(--text-primary)] [&_hr]:border-[var(--border)] [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--accent-blue)] [&_blockquote]:pl-4 [&_blockquote]:text-[var(--text-secondary)]">
          <ReactMarkdown>{narrative.content_md}</ReactMarkdown>
        </article>
      </div>
    </div>
  );
}
