import { apiGet, apiPost, apiDelete } from './client';

export interface SessionProgress {
  processed_frames: number;
  total_frames: number;
  current_interval: number;
}

export interface AnalysisSession {
  id: string;
  source_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  interval_seconds: number;
  progress: SessionProgress | null;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
  created_at: string;
}

export interface AnalysisInterval {
  timestamp: string;
  duration_seconds: number;
  vehicle_counts: Record<string, number>;
  counts_in: Record<string, number>;
  counts_out: Record<string, number>;
  occupancy_ratio: number;
  avg_speed_kmh: number;
  queue_length: number;
}

export function startSession(
  sourceId: string,
  intervalSeconds: number,
  renderVideo: boolean,
): Promise<AnalysisSession> {
  return apiPost<AnalysisSession>(`/sources/${sourceId}/sessions`, {
    interval_seconds: intervalSeconds,
    render_video: renderVideo,
  });
}

export function listSessions(sourceId: string): Promise<AnalysisSession[]> {
  return apiGet<AnalysisSession[]>(`/sources/${sourceId}/sessions`);
}

export function getSession(sessionId: string): Promise<AnalysisSession> {
  return apiGet<AnalysisSession>(`/sessions/${sessionId}`);
}

export function listIntervals(
  sessionId: string,
  start?: string,
  end?: string,
): Promise<AnalysisInterval[]> {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const qs = params.toString();
  return apiGet<AnalysisInterval[]>(
    `/sessions/${sessionId}/intervals${qs ? `?${qs}` : ''}`,
  );
}

export function cancelSession(sessionId: string): Promise<void> {
  return apiDelete(`/sessions/${sessionId}`);
}
