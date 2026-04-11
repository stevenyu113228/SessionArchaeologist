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
    update: (sessionId: string, revision: number, content_md: string) =>
      fetchJson<{ revision: number }>(`/sessions/${sessionId}/narratives/${revision}`, {
        method: 'PUT',
        body: JSON.stringify({ content_md }),
      }),
    score: (sessionId: string, revision: number, score: number) =>
      fetchJson<{ score: number }>(`/sessions/${sessionId}/narratives/${revision}/score`, {
        method: 'POST',
        body: JSON.stringify({ score }),
      }),
    annotate: (sessionId: string, revision: number, annotation: {
      section_path: string; annotation_type: string; content: string; tone?: string;
    }) =>
      fetchJson<{ id: string }>(`/sessions/${sessionId}/narratives/${revision}/annotate`, {
        method: 'POST',
        body: JSON.stringify(annotation),
      }),
    refine: (sessionId: string, revision: number, annotations: {
      section_path: string; annotation_type: string; content: string; tone?: string;
    }[]) =>
      fetchJson<{ revision: number }>(`/sessions/${sessionId}/narratives/${revision}/refine`, {
        method: 'POST',
        body: JSON.stringify({ annotations }),
      }),
    diff: (sessionId: string, rev1: number, rev2: number) =>
      fetchJson<{ diff: string }>(`/sessions/${sessionId}/narratives/diff/${rev1}/${rev2}`),
    expandSection: (sessionId: string, revision: number, section_path: string) =>
      fetchJson<{ revision: number }>(`/sessions/${sessionId}/narratives/${revision}/expand-section`, {
        method: 'POST',
        body: JSON.stringify({ section_path }),
      }),
    shrinkSection: (sessionId: string, revision: number, section_path: string) =>
      fetchJson<{ revision: number }>(`/sessions/${sessionId}/narratives/${revision}/shrink-section`, {
        method: 'POST',
        body: JSON.stringify({ section_path }),
      }),
    translate: (sessionId: string, revision: number, target_lang = 'zh-TW') =>
      fetchJson<{ revision: number }>(`/sessions/${sessionId}/narratives/${revision}/translate`, {
        method: 'POST',
        body: JSON.stringify({ target_lang }),
      }),
  },
  search: {
    query: (sessionId: string, q: string, mode = 'semantic', filters?: Record<string, any>) =>
      fetchJson<{ results: any[] }>(`/sessions/${sessionId}/search`, {
        method: 'POST',
        body: JSON.stringify({ query: q, mode, filters }),
      }),
  },
  pipeline: {
    status: (sessionId: string) => fetchJson<PipelineStatus>(`/pipeline/${sessionId}`),
    chunk: (sessionId: string) =>
      fetchJson<{ chunks_created: number }>(`/sessions/${sessionId}/chunk`, { method: 'POST' }),
    extract: (sessionId: string) =>
      fetchJson<{ status: string; total_chunks: number; pending: number; workers?: number }>(
        `/sessions/${sessionId}/extract`, { method: 'POST' },
      ),
    extractProgress: (sessionId: string, onEvent: (evt: any) => void, onDone: () => void) => {
      const es = new EventSource(`${BASE}/sessions/${sessionId}/extract/progress`);
      es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        onEvent(data);
        if (data.type === 'all_done') {
          es.close();
          onDone();
        }
      };
      es.onerror = () => { es.close(); onDone(); };
      return es;
    },
    synthesize: (sessionId: string) =>
      fetchJson<{ status: string }>(`/sessions/${sessionId}/synthesize`, { method: 'POST' }),
    synthesizeProgress: (sessionId: string, onEvent: (evt: any) => void, onDone: () => void) => {
      const es = new EventSource(`${BASE}/sessions/${sessionId}/synthesize/progress`);
      es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        onEvent(data);
        if (data.type === 'done') {
          es.close();
          onDone();
        }
      };
      es.onerror = () => { es.close(); onDone(); };
      return es;
    },
    runAll: (sessionId: string) =>
      fetchJson<{ status: string }>(`/sessions/${sessionId}/run-pipeline`, { method: 'POST' }),
    runAllProgress: (sessionId: string, onEvent: (evt: any) => void, onDone: () => void) => {
      const es = new EventSource(`${BASE}/sessions/${sessionId}/run-pipeline/progress`);
      es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        onEvent(data);
        if (data.type === 'pipeline_done' || data.type === 'error') {
          es.close();
          onDone();
        }
      };
      es.onerror = () => { es.close(); onDone(); };
      return es;
    },
  },
};
