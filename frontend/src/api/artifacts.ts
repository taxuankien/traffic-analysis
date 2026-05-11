import { API_BASE } from '../lib/constants';
import { apiGet, apiPost } from './client';

export interface Artifact {
  kind: string;
  name: string;
  size_bytes: number;
  mtime: string;
  download_url: string;
  preview_url?: string;
}

export interface RenderVideoStatus {
  session_id: string;
  status: 'running' | 'done' | 'idle';
  available: boolean;
}

export function listArtifacts(sessionId: string): Promise<Artifact[]> {
  return apiGet<Artifact[]>(`/sessions/${sessionId}/artifacts`);
}

export function downloadUrl(path: string): string {
  // Backend returns URLs already starting with /api (e.g. "/api/sessions/.../download/csv")
  // so we must NOT prepend API_BASE again.
  return path;
}

export function bundleUrl(sessionId: string): string {
  return `${API_BASE}/sessions/${sessionId}/download/bundle.zip`;
}

export function requestRenderVideo(sessionId: string): Promise<RenderVideoStatus> {
  return apiPost<RenderVideoStatus>(`/sessions/${sessionId}/render-video`);
}

export function getRenderVideoStatus(sessionId: string): Promise<RenderVideoStatus> {
  return apiGet<RenderVideoStatus>(`/sessions/${sessionId}/render-video`);
}
