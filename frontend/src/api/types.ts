export type SessionListItem = {
  id: string;
  name: string;
  status: string;
  total_turns: number;
  total_tokens_est: number;
  imported_at: string | null;
};

export type SessionDetail = {
  id: string;
  name: string;
  source_path: string;
  imported_at: string | null;
  total_turns: number;
  total_tokens_est: number;
  manifest: Record<string, any> | null;
  status: string;
};

export type Turn = {
  id: string;
  turn_index: number;
  role: string;
  content_text: string;
  tool_calls: any[] | null;
  is_compact_boundary: boolean;
  is_error: boolean;
  token_estimate: number;
  timestamp: string | null;
  model_used: string | null;
  has_thinking: boolean;
  is_sidechain: boolean;
};

export type TurnsPage = {
  items: Turn[];
  total: number;
  offset: number;
  limit: number;
};

export type Chunk = {
  id: string;
  chunk_index: number;
  start_turn: number;
  end_turn: number;
  overlap_start_turn: number | null;
  token_estimate: number;
  hot_zone_count: number;
  contains_compact_boundary: boolean;
  extraction_status: string;
  extraction_result: Record<string, any> | null;
  extraction_model: string | null;
};

export type NarrativeListItem = {
  id: string;
  revision: number;
  parent_revision: number | null;
  synthesis_model: string | null;
  user_score: number | null;
  content_length: number;
  created_at: string | null;
};

export type NarrativeDetail = {
  id: string;
  revision: number;
  parent_revision: number | null;
  content_md: string;
  synthesis_model: string | null;
  user_score: number | null;
  created_at: string | null;
};

export type PipelineStatus = {
  session_id: string;
  session_name: string;
  status: string;
  total_turns: number;
  total_chunks: number;
  extracted_chunks: number;
  total_narratives: number;
};
