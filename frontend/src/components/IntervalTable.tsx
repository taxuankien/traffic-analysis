import type { AnalysisInterval } from '../api/sessions';
import { formatPercent } from '../lib/utils';

interface Props {
  intervals: AnalysisInterval[];
}

export function IntervalTable({ intervals }: Props) {
  if (intervals.length === 0) {
    return (
      <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', padding: 16 }}>
        Chưa có dữ liệu interval.
      </p>
    );
  }

  return (
    <div className="table-container">
      <table>
        <thead>
          <tr>
            <th>Thời gian</th>
            <th>Car</th>
            <th>Moto</th>
            <th>Bus</th>
            <th>Truck</th>
            <th>Occ%</th>
            <th>Speed (km/h)</th>
            <th>Queue</th>
          </tr>
        </thead>
        <tbody>
          {intervals.map((iv, idx) => (
            <tr key={idx} className="animate-fade-in">
              <td style={{ fontFamily: 'monospace', fontSize: '0.8125rem' }}>
                {iv.timestamp.substring(11, 19)}
              </td>
              <td>{iv.vehicle_counts.car ?? 0}</td>
              <td>{iv.vehicle_counts.motorcycle ?? 0}</td>
              <td>{iv.vehicle_counts.bus ?? 0}</td>
              <td>{iv.vehicle_counts.truck ?? 0}</td>
              <td>{formatPercent(iv.occupancy_ratio)}</td>
              <td>{iv.avg_speed_kmh.toFixed(1)}</td>
              <td>{iv.queue_length}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
