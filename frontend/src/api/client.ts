import type {
  SessionListItem, SessionDetail, Turn, TurnsPage,
  Chunk, NarrativeListItem, NarrativeDetail, PipelineStatus,
} from './types';

export type {
  SessionListItem, SessionDetail, Turn, TurnsPage,
  Chunk, NarrativeListItem, NarrativeDetail, PipelineStatus,
};

const BASE = '/api';

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  sessions: {
    list: () => fetchJson<SessionListItem[]>('/sessions'),
    get: (id: string) => fetchJson<SessionDetail>(`/sessions/${id}`),
    import: (path: string, name?: string) =>
      fetchJson<{ id: string }>('/sessions/import', {
        method: 'POST',
        body: JSON.stringify({ path, name }),
      }),
    delete: (id: string) =>
      fetchJson<{ deleted: string }>(`/sessions/${id}`, { method: 'DELETE' }),
  },
  turns: {
    list: (sessionId: string, offset = 0, limit = 50, role?: string, errorsOnly = false) => {
      const params = new URLSearchParams({
        offset: String(offset),
        limit: String(limit),
      });
      if (role) params.set('role', role);
      if (errorsOnly) params.set('errors_only', 'true');
      return fetchJson<TurnsPage>(`/sessions/${sessionId}/turns?${params}`);
    },
    get: (sessionId: string, turnIndex: number) =>
      fetchJson<Turn>(`/sessions/${sessionId}/turns/${turnIndex}`),
  },
  chunks: {
    list: (sessionId: string) => fetchJson<Chunk[]>(`/sessions/${sessionId}/chunks`),
  },
  narratives: {
    list: (sessionId: string) => fetchJson<NarrativeListItem[]>(`/sessions/${sessionId}/narratives`),
    get: (sessionId: string, revision: number) =>
      fetchJson<NarrativeDetail>(`/sessions/${sessionId}/narratives/${revision}`),
    diff: (sessionId: string, rev1: number, rev2: number) =>
      fetchJson<{ diff: string }>(`/sessions/${sessionId}/narratives/diff/${rev1}/${rev2}`),
  },
  pipeline: {
    status: (sessionId: string) => fetchJson<PipelineStatus>(`/pipeline/${sessionId}`),
    chunk: (sessionId: string) =>
      fetchJson<{ chunks_created: number }>(`/sessions/${sessionId}/chunk`, { method: 'POST' }),
    extract: (sessionId: string) =>
      fetchJson<{ extracted: number }>(`/sessions/${sessionId}/extract`, { method: 'POST' }),
    synthesize: (sessionId: string) =>
      fetchJson<{ revision: number }>(`/sessions/${sessionId}/synthesize`, { method: 'POST' }),
  },
};
