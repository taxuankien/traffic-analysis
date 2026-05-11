import { apiGet, apiDelete, uploadFile } from './client';

export interface VideoSourceMetadata {
  fps: number;
  total_frames: number;
  width: number;
  height: number;
}

export interface VideoSource {
  id: string;
  name: string;
  path: string;
  kind: string;
  created_at: string;
  metadata: VideoSourceMetadata | null;
}

export function listSources(): Promise<VideoSource[]> {
  return apiGet<VideoSource[]>('/sources');
}

export function getSource(id: string): Promise<VideoSource> {
  return apiGet<VideoSource>(`/sources/${id}`);
}

export function addSource(
  name: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<VideoSource> {
  const fd = new FormData();
  fd.append('name', name);
  fd.append('file', file);
  return uploadFile('/sources', fd, onProgress) as Promise<VideoSource>;
}

export function deleteSource(id: string, purge = true): Promise<void> {
  return apiDelete(`/sources/${id}?purge=${purge}`);
}
