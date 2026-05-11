import { apiGet, apiPut } from './client';

export interface ROIPolygon {
  name: string;
  points: [number, number][];
}

export interface CountingLine {
  name: string;
  start: [number, number];
  end: [number, number];
  direction: 'in' | 'out' | 'both';
}

export interface ROIConfig {
  reference_frame_index: number;
  roi_polygons: ROIPolygon[];
  counting_lines: CountingLine[];
  pixels_per_meter: number | null;
}

export function getRoi(sourceId: string): Promise<ROIConfig | null> {
  return apiGet<ROIConfig | null>(`/sources/${sourceId}/roi`);
}

export function putRoi(sourceId: string, config: ROIConfig): Promise<ROIConfig> {
  return apiPut<ROIConfig>(`/sources/${sourceId}/roi`, config);
}
