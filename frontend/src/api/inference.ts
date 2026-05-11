import { apiGet, apiPut, apiPost } from './client';

export interface InferenceConfig {
  model: {
    weights: string;
    device: string | null;
    imgsz: number;
    half: boolean;
    max_det: number;
    agnostic_nms: boolean;
  };
  detection: {
    confidence: number;
    iou: number;
    class_ids: number[];
  };
  detection_roi: {
    enabled: boolean;
    bounds: [number, number, number, number];
  };
  tracking: {
    track_activation_threshold: number;
    lost_track_buffer: number;
    minimum_matching_threshold: number;
    minimum_consecutive_frames: number;
  };
  speed: { min_frames: number };
  analysis: { default_interval_seconds: number; frame_skip: number };
  queue: { stopped_speed_kmh: number; window_frames: number };
  vehicle_pce: {
    car: number;
    motorcycle: number;
    bus: number;
    truck: number;
  };
}

export interface FieldMeta {
  type: string;
  label: string;
  description: string;
  min?: number;
  max?: number;
  step?: number;
  default?: unknown;
  ui_hint?: string;
  options?: string[];
}

export interface ModelFileInfo {
  name: string;
  path: string;
  size_mb: number;
}

export function getConfig(): Promise<InferenceConfig> {
  return apiGet<InferenceConfig>('/config/inference');
}

export function putConfig(config: InferenceConfig): Promise<InferenceConfig> {
  return apiPut<InferenceConfig>('/config/inference', config);
}

export function resetConfig(): Promise<InferenceConfig> {
  return apiPost<InferenceConfig>('/config/inference/reset');
}

export function getSchema(): Promise<Record<string, FieldMeta>> {
  return apiGet<Record<string, FieldMeta>>('/config/inference/schema');
}

export function listModels(): Promise<ModelFileInfo[]> {
  return apiGet<ModelFileInfo[]>('/system/models');
}

export interface CatalogModel {
  name: string;
  family: string;
  variant: string;
  size_mb: number;
  downloaded: boolean;
}

export interface DownloadResponse {
  model_name: string;
  status: 'downloading' | 'done' | 'already_exists' | 'failed';
  message: string;
}

export function getCatalog(): Promise<CatalogModel[]> {
  return apiGet<CatalogModel[]>('/system/models/catalog');
}

export function downloadModel(modelName: string): Promise<DownloadResponse> {
  return apiPost<DownloadResponse>('/system/models/download', { model_name: modelName });
}
