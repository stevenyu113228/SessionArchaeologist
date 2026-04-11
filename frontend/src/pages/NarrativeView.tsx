import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ChevronLeft, Download, GitCompare, Star,
  MessageSquarePlus, RefreshCw, Eye, Pen, Search,
  Plus, Minus, Languages, Loader2,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../api/client';
import type { NarrativeDetail, NarrativeListItem } from '../api/types';
import ExportModal from '../components/ExportModal';

type AnnotationType = 'correction' | 'injection' | 'needs_detail' | 'tone_change' | 'add_subsection';
type PendingAnnotation = {
  section_path: string;
  annotation_type: AnnotationType;
  content: string;
  tone: string;
};

export default function NarrativeView() {
  const { id, revision } = useParams<{ id: string; revision: string }>();
  const [narrative, setNarrative] = useState<NarrativeDetail | null>(null);
  const [allRevisions, setAllRevisions] = useState<NarrativeListItem[]>([]);
  const [diffText, setDiffText] = useState<string | null>(null);
  const [diffWith, setDiffWith] = useState<number | null>(null);

  // Editor state
  const [mode, setMode] = useState<'view' | 'edit' | 'annotate'>('view');
  const [editContent, setEditContent] = useState('');
  const [annotations, setAnnotations] = useState<PendingAnnotation[]>([]);
  const [newAnnotation, setNewAnnotation] = useState<PendingAnnotation>({
    section_path: '', annotation_type: 'correction', content: '', tone: '',
  });
  const [refining, setRefining] = useState(false);
  const [sectionLoading, setSectionLoading] = useState<string | null>(null); // section_path being expanded/shrunk
  const [translating, setTranslating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [score, setScore] = useState<number | null>(null);

  // Export modal
  const [exportOpen, setExportOpen] = useState(false);

  // Search panel
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);

  const load = useCallback(async () => {
    if (!id || !revision) return;
    const [n, revs] = await Promise.all([
      api.narratives.get(id, parseInt(revision)),
      api.narratives.list(id),
    ]);
    setNarrative(n);
    setAllRevisions(revs);
    setEditContent(n.content_md);
    setScore(n.user_score);
  }, [id, revision]);

  useEffect(() => { load(); }, [load]);

  const showDiff = async (otherRev: number) => {
    if (!id || !revision) return;
    const rev = parseInt(revision);
    const { diff } = await api.narratives.diff(id, Math.min(rev, otherRev), Math.max(rev, otherRev));
    setDiffText(diff);
    setDiffWith(otherRev);
  };

  const handleSaveEdit = async () => {
    if (!id || !revision || !narrative) return;
    setSaving(true);
    try {
      const { revision: newRev } = await api.narratives.update(id, narrative.revision, editContent);
      window.location.href = `/session/${id}/narrative/${newRev}`;
    } finally {
      setSaving(false);
    }
  };

  const addAnnotation = () => {
    if (!newAnnotation.section_path || !newAnnotation.content) return;
    setAnnotations([...annotations, { ...newAnnotation }]);
    setNewAnnotation({ section_path: '', annotation_type: 'correction', content: '', tone: '' });
  };

  const removeAnnotation = (idx: number) => {
    setAnnotations(annotations.filter((_, i) => i !== idx));
  };

  const submitRefinement = async () => {
    if (!id || !revision || annotations.length === 0) return;
    setRefining(true);
    try {
      const { revision: newRev } = await api.narratives.refine(id, parseInt(revision), annotations);
      setAnnotations([]);
      window.location.href = `/session/${id}/narrative/${newRev}`;
    } finally {
      setRefining(false);
    }
  };

  const handleScore = async (s: number) => {
    if (!id || !narrative) return;
    setScore(s);
    await api.narratives.score(id, narrative.revision, s);
  };

  const doSearch = async () => {
    if (!id || !searchQuery.trim()) return;
    try {
      const { results } = await api.search.query(id, searchQuery);
      setSearchResults(results);
    } catch {
      setSearchResults([]);
    }
  };

  const handleExpandSection = async (sectionSlug: string) => {
    if (!id || !narrative) return;
    setSectionLoading(sectionSlug);
    try {
      const { revision: newRev } = await api.narratives.expandSection(id, narrative.revision, sectionSlug);
      window.location.href = `/session/${id}/narrative/${newRev}`;
    } finally {
      setSectionLoading(null);
    }
  };

  const handleShrinkSection = async (sectionSlug: string) => {
    if (!id || !narrative) return;
    setSectionLoading(sectionSlug);
    try {
      const { revision: newRev } = await api.narratives.shrinkSection(id, narrative.revision, sectionSlug);
      window.location.href = `/session/${id}/narrative/${newRev}`;
    } finally {
      setSectionLoading(null);
    }
  };

  const handleTranslate = async () => {
    if (!id || !narrative) return;
    setTranslating(true);
    try {
      const { revision: newRev } = await api.narratives.translate(id, narrative.revision, 'zh-TW');
      window.location.href = `/session/${id}/narrative/${newRev}`;
    } finally {
      setTranslating(false);
    }
  };

  if (!narrative) return <div className="p-6 text-[var(--text-muted)]">Loading...</div>;

  // Parse sections from markdown for annotation dropdown
  const sections = narrative.content_md
    .split('\n')
    .filter(l => l.startsWith('#'))
    .map(l => {
      const text = l.replace(/^#+\s*/, '').trim();
      const slug = text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
      return { text, slug };
    });

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left panel — Narrative (60%) */}
      <div className="flex-1 min-w-0 flex flex-col border-r border-[var(--border)]">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between p-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
          <div className="flex items-center gap-3">
            <Link to={`/session/${id}`} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
              <ChevronLeft size={18} />
            </Link>
            <div>
              <h1 className="text-base font-bold">Revision {narrative.revision}</h1>
              <p className="text-xs text-[var(--text-muted)]">
                {narrative.synthesis_model} · {narrative.content_md.length.toLocaleString()} chars
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Mode toggles */}
            <div className="flex bg-[var(--bg-primary)] rounded border border-[var(--border)]">
              {([
                { m: 'view' as const, icon: <Eye size={14} />, label: 'View' },
                { m: 'edit' as const, icon: <Pen size={14} />, label: 'Edit' },
                { m: 'annotate' as const, icon: <MessageSquarePlus size={14} />, label: 'Annotate' },
              ]).map(({ m, icon, label }) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium transition-colors ${
                    mode === m
                      ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {icon} {label}
                </button>
              ))}
            </div>
            {/* Score */}
            <div className="flex items-center gap-1 ml-2">
              {[1, 2, 3, 4, 5].map(s => (
                <button
                  key={s}
                  onClick={() => handleScore(s)}
                  className={`p-0.5 ${score && score >= s ? 'text-[var(--accent-yellow)]' : 'text-[var(--text-muted)]'}`}
                >
                  <Star size={14} fill={score && score >= s ? 'currentColor' : 'none'} />
                </button>
              ))}
            </div>
            {/* Diff */}
            {allRevisions.length > 1 && (
              <select
                onChange={e => e.target.value && showDiff(parseInt(e.target.value))}
                value={diffWith ?? ''}
                className="px-2 py-1.5 bg-[var(--bg-primary)] border border-[var(--border)] rounded text-xs text-[var(--text-primary)]"
              >
                <option value="">Diff...</option>
                {allRevisions.filter(r => r.revision !== narrative.revision).map(r => (
                  <option key={r.revision} value={r.revision}>Rev {r.revision}</option>
                ))}
              </select>
            )}
            <button
              onClick={handleTranslate}
              disabled={translating}
              className="flex items-center gap-1 px-2 py-1.5 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--border)] rounded"
              title="Translate to 繁體中文"
            >
              {translating ? <Loader2 size={14} className="animate-spin" /> : <Languages size={14} />}
              中文
            </button>
            <button onClick={() => setExportOpen(true)} className="p-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
              <Download size={16} />
            </button>
          </div>
        </div>

        {/* Diff banner */}
        {diffText !== null && (
          <div className="shrink-0 bg-[var(--bg-secondary)] border-b border-[var(--border)] p-3 max-h-60 overflow-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium flex items-center gap-1"><GitCompare size={12} /> Diff with Rev {diffWith}</span>
              <button onClick={() => { setDiffText(null); setDiffWith(null); }} className="text-xs text-[var(--text-muted)]">Close</button>
            </div>
            <pre className="text-xs mono">{diffText.split('\n').map((line, i) => (
              <div key={i} className={
                line.startsWith('+') && !line.startsWith('+++') ? 'text-[var(--accent-green)] bg-[var(--accent-green)]/10'
                : line.startsWith('-') && !line.startsWith('---') ? 'text-[var(--accent-red)] bg-[var(--accent-red)]/10'
                : line.startsWith('@@') ? 'text-[var(--accent-blue)]' : 'text-[var(--text-muted)]'
              }>{line}</div>
            ))}</pre>
          </div>
        )}

        {/* Content area */}
        <div className="flex-1 overflow-auto p-6">
          {mode === 'view' && (
            <article className="prose-custom max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                h2: ({ children }) => {
                  const text = String(children);
                  const slug = text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
                  const isLoading = sectionLoading === slug;
                  return (
                    <div className="flex items-center gap-2 group">
                      <h2>{children}</h2>
                      <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 shrink-0">
                        <button
                          onClick={() => handleExpandSection(slug)}
                          disabled={isLoading}
                          className="p-1 rounded text-[var(--accent-green)] hover:bg-[var(--accent-green)]/20"
                          title="Expand with evidence from source"
                        >
                          {isLoading ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                        </button>
                        <button
                          onClick={() => handleShrinkSection(slug)}
                          disabled={isLoading}
                          className="p-1 rounded text-[var(--accent-yellow)] hover:bg-[var(--accent-yellow)]/20"
                          title="Shrink section"
                        >
                          <Minus size={14} />
                        </button>
                      </div>
                    </div>
                  );
                },
              }}>{narrative.content_md}</ReactMarkdown>
            </article>
          )}
          {mode === 'edit' && (
            <div className="h-full flex flex-col gap-3">
              <textarea
                value={editContent}
                onChange={e => setEditContent(e.target.value)}
                className="flex-1 w-full bg-[var(--bg-primary)] border border-[var(--border)] rounded-lg p-4 text-sm mono text-[var(--text-primary)] resize-none focus:outline-none focus:border-[var(--accent-blue)]"
                spellCheck={false}
              />
              <div className="flex justify-end gap-2">
                <button onClick={() => { setMode('view'); setEditContent(narrative.content_md); }}
                  className="px-4 py-2 text-sm text-[var(--text-secondary)] border border-[var(--border)] rounded">
                  Cancel
                </button>
                <button onClick={handleSaveEdit} disabled={saving}
                  className="px-4 py-2 text-sm bg-[var(--accent-blue)] text-black font-medium rounded disabled:opacity-50">
                  {saving ? 'Saving...' : 'Save as New Revision'}
                </button>
              </div>
            </div>
          )}
          {mode === 'annotate' && (
            <div className="flex flex-col gap-4">
              <article className="prose-custom max-w-none opacity-80">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{narrative.content_md}</ReactMarkdown>
              </article>
            </div>
          )}
        </div>
      </div>

      {/* Right panel — Annotations + Search (40%) */}
      <div className="w-[440px] shrink-0 flex flex-col bg-[var(--bg-secondary)]">
        {/* Panel tabs */}
        <div className="flex border-b border-[var(--border)]">
          <button
            onClick={() => setSearchOpen(false)}
            className={`flex-1 px-4 py-2.5 text-xs font-medium ${!searchOpen ? 'border-b-2 border-[var(--accent-blue)] text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}
          >
            <MessageSquarePlus size={12} className="inline mr-1" /> Annotations ({annotations.length})
          </button>
          <button
            onClick={() => setSearchOpen(true)}
            className={`flex-1 px-4 py-2.5 text-xs font-medium ${searchOpen ? 'border-b-2 border-[var(--accent-blue)] text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}
          >
            <Search size={12} className="inline mr-1" /> Source Search
          </button>
        </div>

        {!searchOpen ? (
          <div className="flex-1 overflow-auto p-4 flex flex-col gap-4">
            {/* New annotation form */}
            <div className="bg-[var(--bg-primary)] border border-[var(--border)] rounded-lg p-3 space-y-3">
              <h3 className="text-xs font-semibold text-[var(--text-secondary)]">Add Annotation</h3>
              <select
                value={newAnnotation.section_path}
                onChange={e => setNewAnnotation({ ...newAnnotation, section_path: e.target.value })}
                className="w-full px-2 py-1.5 bg-[var(--bg-secondary)] border border-[var(--border)] rounded text-xs text-[var(--text-primary)]"
              >
                <option value="">Select section...</option>
                {sections.map(s => (
                  <option key={s.slug} value={s.slug}>{s.text}</option>
                ))}
              </select>
              <select
                value={newAnnotation.annotation_type}
                onChange={e => setNewAnnotation({ ...newAnnotation, annotation_type: e.target.value as AnnotationType })}
                className="w-full px-2 py-1.5 bg-[var(--bg-secondary)] border border-[var(--border)] rounded text-xs text-[var(--text-primary)]"
              >
                <option value="correction">Correction — fix factual errors</option>
                <option value="injection">Injection — add context AI couldn't know</option>
                <option value="needs_detail">Needs Detail — enrich from raw data</option>
                <option value="add_subsection">Add Subsection — AI searches & writes new content</option>
                <option value="tone_change">Tone Change — adjust writing style</option>
              </select>
              {newAnnotation.annotation_type === 'tone_change' && (
                <select
                  value={newAnnotation.tone}
                  onChange={e => setNewAnnotation({ ...newAnnotation, tone: e.target.value })}
                  className="w-full px-2 py-1.5 bg-[var(--bg-secondary)] border border-[var(--border)] rounded text-xs text-[var(--text-primary)]"
                >
                  <option value="">Select tone...</option>
                  <option value="technical_deep_dive">Technical Deep Dive</option>
                  <option value="war_story">War Story / Conference Talk</option>
                  <option value="executive_summary">Executive Summary</option>
                </select>
              )}
              <textarea
                value={newAnnotation.content}
                onChange={e => setNewAnnotation({ ...newAnnotation, content: e.target.value })}
                placeholder={
                  newAnnotation.annotation_type === 'correction'
                    ? 'What should be corrected...'
                    : newAnnotation.annotation_type === 'injection'
                    ? 'Additional context to add...'
                    : newAnnotation.annotation_type === 'needs_detail'
                    ? 'What details are missing...'
                    : newAnnotation.annotation_type === 'add_subsection'
                    ? 'Topic for new subsection (AI will search source data)...'
                    : 'Describe desired tone...'
                }
                rows={3}
                className="w-full px-2 py-1.5 bg-[var(--bg-secondary)] border border-[var(--border)] rounded text-xs text-[var(--text-primary)] resize-none placeholder-[var(--text-muted)]"
              />
              <button onClick={addAnnotation}
                className="w-full px-3 py-1.5 text-xs font-medium bg-[var(--accent-blue)]/20 text-[var(--accent-blue)] border border-[var(--accent-blue)]/30 rounded hover:bg-[var(--accent-blue)]/30">
                Add Annotation
              </button>
            </div>

            {/* Pending annotations */}
            {annotations.map((ann, i) => (
              <div key={i} className="bg-[var(--bg-primary)] border border-[var(--border)] rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <TypeBadge type={ann.annotation_type} />
                    <span className="text-xs mono text-[var(--text-muted)]">{ann.section_path}</span>
                  </div>
                  <button onClick={() => removeAnnotation(i)} className="text-xs text-[var(--accent-red)] hover:underline">
                    Remove
                  </button>
                </div>
                <p className="text-xs text-[var(--text-secondary)]">{ann.content || `tone: ${ann.tone}`}</p>
              </div>
            ))}

            {/* Submit refinement */}
            {annotations.length > 0 && (
              <button
                onClick={submitRefinement}
                disabled={refining}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[var(--accent-green)] text-black font-medium rounded-lg text-sm disabled:opacity-50"
              >
                <RefreshCw size={14} className={refining ? 'animate-spin' : ''} />
                {refining ? 'Refining...' : `Submit ${annotations.length} Annotation(s)`}
              </button>
            )}

            {/* Revision history */}
            <div className="mt-4">
              <h3 className="text-xs font-semibold text-[var(--text-secondary)] mb-2">Revision History</h3>
              <div className="space-y-1">
                {allRevisions.map(r => (
                  <Link
                    key={r.revision}
                    to={`/session/${id}/narrative/${r.revision}`}
                    className={`block px-3 py-2 rounded text-xs no-underline transition-colors ${
                      r.revision === narrative.revision
                        ? 'bg-[var(--accent-blue)]/10 text-[var(--accent-blue)] border border-[var(--accent-blue)]/30'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
                    }`}
                  >
                    <div className="flex justify-between">
                      <span>Rev {r.revision} {r.parent_revision ? `(from ${r.parent_revision})` : ''}</span>
                      <span className="text-[var(--text-muted)]">
                        {r.user_score ? '★'.repeat(r.user_score) : ''}
                        {' '}{r.content_length.toLocaleString()} chars
                      </span>
                    </div>
                    <div className="text-[var(--text-muted)] mt-0.5">
                      {r.synthesis_model} · {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* Search panel */
          <div className="flex-1 overflow-auto p-4 flex flex-col gap-3">
            <div className="flex gap-2">
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && doSearch()}
                placeholder="Search raw session data..."
                className="flex-1 px-3 py-1.5 bg-[var(--bg-primary)] border border-[var(--border)] rounded text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)]"
              />
              <button onClick={doSearch} className="px-3 py-1.5 bg-[var(--accent-blue)]/20 text-[var(--accent-blue)] rounded text-xs border border-[var(--accent-blue)]/30">
                Search
              </button>
            </div>
            {searchResults.length > 0 ? (
              <div className="space-y-2">
                {searchResults.map((r: any, i: number) => (
                  <div key={i} className="bg-[var(--bg-primary)] border border-[var(--border)] rounded p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs font-medium ${r.role === 'user' ? 'text-[var(--accent-green)]' : 'text-[var(--accent-blue)]'}`}>
                        {r.role}
                      </span>
                      <span className="text-xs text-[var(--text-muted)]">Turn #{r.turn_index}</span>
                      {r.score && <span className="text-xs text-[var(--accent-yellow)]">Score: {r.score.toFixed(2)}</span>}
                    </div>
                    <pre className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap break-words m-0">
                      {r.content_text?.slice(0, 500)}{r.content_text?.length > 500 ? '...' : ''}
                    </pre>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-muted)] text-center py-8">
                Search raw session data to find source material for the narrative.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Export modal */}
      {exportOpen && id && (
        <ExportModal sessionId={id} revision={narrative.revision} onClose={() => setExportOpen(false)} />
      )}

      <style>{`
        .prose-custom h1 { font-size: 1.5rem; font-weight: 700; margin: 0 0 1rem; }
        .prose-custom h2 { font-size: 1.25rem; font-weight: 600; margin: 2rem 0 0.75rem; color: var(--text-primary); }
        .prose-custom h3 { font-size: 1.1rem; font-weight: 600; margin: 1.5rem 0 0.5rem; }
        .prose-custom p { font-size: 0.875rem; line-height: 1.7; margin: 0 0 0.75rem; color: var(--text-secondary); }
        .prose-custom strong { color: var(--text-primary); }
        .prose-custom code { background: var(--bg-tertiary); padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-size: 0.75rem; }
        .prose-custom pre { background: var(--bg-primary); border: 1px solid var(--border); border-radius: 0.5rem; padding: 1rem; overflow: auto; font-size: 0.75rem; margin: 0.75rem 0; }
        .prose-custom pre code { background: none; padding: 0; }
        .prose-custom ul, .prose-custom ol { font-size: 0.875rem; color: var(--text-secondary); padding-left: 1.5rem; margin: 0 0 0.75rem; }
        .prose-custom li { margin: 0.25rem 0; }
        .prose-custom table { font-size: 0.875rem; width: 100%; border-collapse: collapse; margin: 0.75rem 0; }
        .prose-custom th { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); font-weight: 600; }
        .prose-custom td { padding: 0.5rem; border-bottom: 1px solid var(--border); }
        .prose-custom a { color: var(--accent-blue); text-decoration: none; }
        .prose-custom a:hover { text-decoration: underline; }
        .prose-custom hr { border-color: var(--border); margin: 1.5rem 0; }
        .prose-custom blockquote { border-left: 2px solid var(--accent-blue); padding-left: 1rem; color: var(--text-secondary); margin: 0.75rem 0; }
      `}</style>
    </div>
  );
}

function TypeBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    correction: 'bg-[var(--accent-red)]/20 text-[var(--accent-red)]',
    injection: 'bg-[var(--accent-green)]/20 text-[var(--accent-green)]',
    needs_detail: 'bg-[var(--accent-yellow)]/20 text-[var(--accent-yellow)]',
    add_subsection: 'bg-[var(--accent-blue)]/20 text-[var(--accent-blue)]',
    tone_change: 'bg-[var(--accent-purple)]/20 text-[var(--accent-purple)]',
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${styles[type] || ''}`}>
      {type.replace('_', ' ')}
    </span>
  );
}
