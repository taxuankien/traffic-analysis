import { apiGet } from './client';

export interface SystemMonitor {
  cpu_percent: number;
  ram_percent: number;
  gpu: {
    name: string;
    util_percent: number;
    mem_used_mb: number;
    mem_total_mb: number;
  }[];
}

export function getHealth(): Promise<{ status: string }> {
  return apiGet<{ status: string }>('/health');
}

export function getMonitor(): Promise<SystemMonitor> {
  return apiGet<SystemMonitor>('/system/monitor');
}
