import { API_BASE } from '../lib/constants';
import { apiPost } from './client';

export interface Detection {
  class_id: number;
  class_name: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
}

export interface TestDetectTimings {
  inference_ms: number;
  annotation_ms: number;
  total_ms: number;
  fps_estimate: number;
  device: string;
  image_size: [number, number];
}

export interface TestDetectResult {
  frame_index: number;
  detections: Detection[];
  summary: Record<string, number>;
  annotated_url: string;
  timings: TestDetectTimings;
}

export function frameUrl(sourceId: string, time: number): string {
  return `${API_BASE}/sources/${sourceId}/frame?time=${time}`;
}

export function testDetect(
  sourceId: string,
  time: number,
  annotate = true,
): Promise<TestDetectResult> {
  return apiPost<TestDetectResult>(`/sources/${sourceId}/test-detect`, {
    time,
    annotate,
  });
}

export function saveFrame(
  sourceId: string,
  time: number,
): Promise<{ url: string }> {
  return apiPost<{ url: string }>(`/sources/${sourceId}/frame/save`, {
    time,
    annotate: false,
  });
}
