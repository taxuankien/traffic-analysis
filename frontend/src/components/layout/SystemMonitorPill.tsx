import { useQuery } from '@tanstack/react-query';
import { Cpu, Activity } from 'lucide-react';
import { getMonitor, type SystemMonitor } from '../../api/system';

export function SystemMonitorPill() {
  const { data } = useQuery<SystemMonitor>({
    queryKey: ['system-monitor'],
    queryFn: getMonitor,
    refetchInterval: 5000,
    retry: false,
  });

  if (!data) return null;

  const gpuInfo = data.gpu?.[0];

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '6px 14px',
        background: 'rgba(148, 163, 184, 0.08)',
        borderRadius: 9999,
        fontSize: '0.75rem',
        color: 'var(--color-text-secondary)',
      }}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <Cpu size={13} />
        {data.cpu_percent.toFixed(0)}%
      </span>
      {gpuInfo && (
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Activity size={13} />
          GPU {gpuInfo.util_percent.toFixed(0)}%
        </span>
      )}
    </div>
  );
}
