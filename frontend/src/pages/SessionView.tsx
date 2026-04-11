import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ChevronLeft, Play, Zap, FileText, AlertCircle, Flame, BookOpen } from 'lucide-react';
import { api } from '../api/client';
import type { SessionDetail, Chunk, Turn, TurnsPage, NarrativeListItem, PipelineStatus } from '../api/types';

export default function SessionView() {
  const { id } = useParams<{ id: string }>();
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [turnsPage, setTurnsPage] = useState<TurnsPage | null>(null);
  const [narratives, setNarratives] = useState<NarrativeListItem[]>([]);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [turnsOffset, setTurnsOffset] = useState(0);
  const [loading, setLoading] = useState('');
  const [tab, setTab] = useState<'overview' | 'turns' | 'timeline' | 'narratives'>('overview');

  const load = async () => {
    if (!id) return;
    const [s, c, t, n, p] = await Promise.all([
      api.sessions.get(id),
      api.chunks.list(id).catch(() => []),
      api.turns.list(id, 0, 50),
      api.narratives.list(id).catch(() => []),
      api.pipeline.status(id).catch(() => null),
    ]);
    setSession(s);
    setChunks(c);
    setTurnsPage(t);
    setNarratives(n);
    setPipeline(p);
  };

  useEffect(() => { load(); }, [id]);

  const loadTurns = async (offset: number) => {
    if (!id) return;
    const t = await api.turns.list(id, offset, 50);
    setTurnsPage(t);
    setTurnsOffset(offset);
  };

  const runStage = async (stage: 'chunk' | 'extract' | 'synthesize') => {
    if (!id) return;
    setLoading(stage);
    try {
      if (stage === 'chunk') await api.pipeline.chunk(id);
      else if (stage === 'extract') await api.pipeline.extract(id);
      else if (stage === 'synthesize') await api.pipeline.synthesize(id);
      await load();
    } finally {
      setLoading('');
    }
  };

  if (!session) return <div className="p-6 text-[var(--text-muted)]">Loading...</div>;

  const manifest = session.manifest || {};
  const hotZones = manifest.hot_zones || [];
  const errorDensity = manifest.error_density || [];
  const toolTimeline = manifest.tool_timeline || [];

  return (
    <div className="p-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link to="/" className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
          <ChevronLeft size={20} />
        </Link>
        <div>
          <h1 className="text-xl font-bold">{session.name}</h1>
          <p className="text-xs text-[var(--text-muted)]">{session.id}</p>
        </div>
      </div>

      {/* Pipeline control */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4 mb-6">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Play size={16} /> Pipeline Control
        </h2>
        <div className="flex gap-2">
          {[
            { stage: 'chunk' as const, label: 'Chunk', enabled: session.status === 'imported' },
            { stage: 'extract' as const, label: 'Extract', enabled: session.status === 'chunked' },
            { stage: 'synthesize' as const, label: 'Synthesize', enabled: session.status === 'extracted' },
          ].map(({ stage, label, enabled }) => (
            <button
              key={stage}
              onClick={() => runStage(stage)}
              disabled={!enabled || loading !== ''}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                enabled
                  ? 'bg-[var(--accent-green)]/20 text-[var(--accent-green)] hover:bg-[var(--accent-green)]/30 border border-[var(--accent-green)]/30'
                  : 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] cursor-not-allowed border border-[var(--border)]'
              }`}
            >
              {loading === stage ? `Running ${label}...` : label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2 text-sm">
            <span className="text-[var(--text-secondary)]">Status:</span>
            <span className="text-[var(--accent-blue)] font-medium">{session.status}</span>
            {pipeline && (
              <span className="text-[var(--text-muted)]">
                ({pipeline.total_chunks} chunks, {pipeline.extracted_chunks} extracted, {pipeline.total_narratives} narratives)
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-[var(--border)]">
        {(['overview', 'turns', 'timeline', 'narratives'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? 'border-[var(--accent-blue)] text-[var(--text-primary)]'
                : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <div className="grid grid-cols-2 gap-4">
          {/* Manifest stats */}
          <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3">Session Stats</h3>
            <div className="space-y-2 text-sm">
              <Row label="Total turns" value={session.total_turns} />
              <Row label="Total tokens" value={session.total_tokens_est.toLocaleString()} />
              <Row label="Errors" value={manifest.error_count || 0} color="red" />
              <Row label="Hot zones" value={hotZones.length} color="yellow" />
              <Row label="Compact boundaries" value={(manifest.compact_boundaries || []).length} color="blue" />
              <Row label="Thinking turns" value={manifest.thinking_count || 0} />
              {manifest.time_range && (
                <>
                  <Row label="Duration" value={`${manifest.time_range.duration_hours?.toFixed(1)}h`} />
                  <Row label="Start" value={manifest.time_range.start?.substring(0, 19)} />
                  <Row label="End" value={manifest.time_range.end?.substring(0, 19)} />
                </>
              )}
            </div>
          </div>

          {/* Tool usage */}
          <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Zap size={14} /> Tool Usage
            </h3>
            <div className="space-y-1">
              {toolTimeline.slice(0, 15).map((t: any) => (
                <div key={t.tool} className="flex justify-between text-sm">
                  <span className="mono text-[var(--text-secondary)]">{t.tool}</span>
                  <span>{t.count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Hot zones */}
          {hotZones.length > 0 && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Flame size={14} className="text-[var(--accent-yellow)]" /> Hot Zones
              </h3>
              <div className="space-y-1 text-sm">
                {hotZones.map((hz: any, i: number) => (
                  <div key={i} className="flex justify-between">
                    <span>Turns {hz.start_turn}–{hz.end_turn}</span>
                    <span className="text-[var(--accent-yellow)]">{hz.turn_count} turns</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chunks */}
          {chunks.length > 0 && (
            <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4">
              <h3 className="text-sm font-semibold mb-3">Chunks</h3>
              <div className="space-y-1 text-sm">
                {chunks.map(c => (
                  <div key={c.id} className="flex justify-between items-center">
                    <span>
                      Chunk {c.chunk_index}: turns {c.start_turn}–{c.end_turn}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="mono text-[var(--text-muted)]">~{c.token_estimate.toLocaleString()} tok</span>
                      <span className={`text-xs ${c.extraction_status === 'done' ? 'text-[var(--accent-green)]' : 'text-[var(--text-muted)]'}`}>
                        {c.extraction_status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'turns' && turnsPage && (
        <div>
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm text-[var(--text-secondary)]">
              Showing {turnsOffset + 1}–{Math.min(turnsOffset + 50, turnsPage.total)} of {turnsPage.total}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => loadTurns(Math.max(0, turnsOffset - 50))}
                disabled={turnsOffset === 0}
                className="px-3 py-1 text-sm bg-[var(--bg-secondary)] border border-[var(--border)] rounded disabled:opacity-30"
              >
                Prev
              </button>
              <button
                onClick={() => loadTurns(turnsOffset + 50)}
                disabled={turnsOffset + 50 >= turnsPage.total}
                className="px-3 py-1 text-sm bg-[var(--bg-secondary)] border border-[var(--border)] rounded disabled:opacity-30"
              >
                Next
              </button>
            </div>
          </div>
          <div className="space-y-2">
            {turnsPage.items.map(turn => (
              <TurnCard key={turn.id} turn={turn} />
            ))}
          </div>
        </div>
      )}

      {tab === 'timeline' && (
        <TimelineBar turns={turnsPage?.total || session.total_turns} manifest={manifest} chunks={chunks} />
      )}

      {tab === 'narratives' && (
        <div>
          {narratives.length === 0 ? (
            <p className="text-[var(--text-muted)] text-sm py-8 text-center">
              No narratives yet. Run synthesis first.
            </p>
          ) : (
            <div className="space-y-2">
              {narratives.map(n => (
                <Link
                  key={n.id}
                  to={`/session/${id}/narrative/${n.revision}`}
                  className="block bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4 hover:border-[var(--accent-blue)] transition-colors no-underline"
                >
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-3">
                      <BookOpen size={16} className="text-[var(--accent-blue)]" />
                      <span className="font-medium">Revision {n.revision}</span>
                      {n.parent_revision && (
                        <span className="text-xs text-[var(--text-muted)]">from rev {n.parent_revision}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-sm text-[var(--text-secondary)]">
                      <span>{n.content_length.toLocaleString()} chars</span>
                      <span>{n.synthesis_model}</span>
                      <span>{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value, color }: { label: string; value: any; color?: string }) {
  const colorClass = color === 'red' ? 'text-[var(--accent-red)]'
    : color === 'yellow' ? 'text-[var(--accent-yellow)]'
    : color === 'blue' ? 'text-[var(--accent-blue)]'
    : '';
  return (
    <div className="flex justify-between">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className={colorClass}>{value}</span>
    </div>
  );
}

function TurnCard({ turn }: { turn: Turn }) {
  const [expanded, setExpanded] = useState(false);
  const roleColors: Record<string, string> = {
    user: 'border-l-[var(--accent-green)]',
    assistant: 'border-l-[var(--accent-blue)]',
    system: 'border-l-[var(--accent-yellow)]',
  };
  const preview = turn.content_text.slice(0, 200);

  return (
    <div
      className={`bg-[var(--bg-secondary)] border border-[var(--border)] border-l-2 ${roleColors[turn.role] || ''} rounded p-3 cursor-pointer`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="mono text-xs text-[var(--text-muted)]">#{turn.turn_index}</span>
        <span className={`text-xs font-medium ${
          turn.role === 'user' ? 'text-[var(--accent-green)]'
            : turn.role === 'assistant' ? 'text-[var(--accent-blue)]'
            : 'text-[var(--accent-yellow)]'
        }`}>
          {turn.role}
        </span>
        {turn.is_error && <AlertCircle size={12} className="text-[var(--accent-red)]" />}
        {turn.is_compact_boundary && <span className="text-xs text-[var(--accent-purple)]">compact</span>}
        {turn.tool_calls && turn.tool_calls.length > 0 && (
          <span className="text-xs text-[var(--text-muted)]">
            {turn.tool_calls.map((tc: any) => tc.tool_name).join(', ')}
          </span>
        )}
        <span className="ml-auto text-xs text-[var(--text-muted)] mono">{turn.token_estimate} tok</span>
      </div>
      <pre className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap break-words m-0">
        {expanded ? turn.content_text : preview}{!expanded && turn.content_text.length > 200 ? '...' : ''}
      </pre>
    </div>
  );
}

function TimelineBar({ turns, manifest, chunks }: { turns: number; manifest: any; chunks: Chunk[] }) {
  const hotZones = manifest.hot_zones || [];
  const compactBounds = new Set(manifest.compact_boundaries || []);
  const errorDensity = manifest.error_density || [];

  if (turns === 0) return null;

  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-4">Session Timeline</h3>

      {/* Timeline bar */}
      <div className="relative h-10 bg-[var(--bg-primary)] rounded border border-[var(--border)] mb-4">
        {/* Hot zones */}
        {hotZones.map((hz: any, i: number) => (
          <div
            key={`hz-${i}`}
            className="absolute top-0 h-full bg-[var(--accent-yellow)]/20 border-x border-[var(--accent-yellow)]/40"
            style={{
              left: `${(hz.start_turn / turns) * 100}%`,
              width: `${((hz.end_turn - hz.start_turn) / turns) * 100}%`,
            }}
            title={`Hot zone: turns ${hz.start_turn}-${hz.end_turn} (${hz.turn_count} turns)`}
          />
        ))}

        {/* Error density */}
        {errorDensity.map((ed: any, i: number) => (
          <div
            key={`ed-${i}`}
            className="absolute bottom-0 bg-[var(--accent-red)]"
            style={{
              left: `${(ed.start_turn / turns) * 100}%`,
              width: `${((ed.end_turn - ed.start_turn) / turns) * 100}%`,
              height: `${Math.min(100, ed.density * 100)}%`,
              opacity: 0.4,
            }}
            title={`${ed.error_count} errors`}
          />
        ))}

        {/* Compact boundaries */}
        {Array.from(compactBounds).map((cb: any) => (
          <div
            key={`cb-${cb}`}
            className="absolute top-0 h-full w-0.5 bg-[var(--accent-purple)]"
            style={{ left: `${(cb / turns) * 100}%` }}
            title={`Compact boundary at turn ${cb}`}
          />
        ))}

        {/* Chunk boundaries */}
        {chunks.map(c => (
          <div
            key={c.id}
            className="absolute top-0 h-full border-l border-dashed border-[var(--accent-blue)]/50"
            style={{ left: `${(c.start_turn / turns) * 100}%` }}
            title={`Chunk ${c.chunk_index}: turns ${c.start_turn}-${c.end_turn}`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="flex gap-4 text-xs text-[var(--text-secondary)]">
        <span className="flex items-center gap-1"><span className="w-3 h-3 bg-[var(--accent-yellow)]/30 rounded" /> Hot zones</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 bg-[var(--accent-red)]/40 rounded" /> Error density</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[var(--accent-purple)]" /> Compact boundary</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 border-t border-dashed border-[var(--accent-blue)]" /> Chunk boundary</span>
      </div>
    </div>
  );
}
