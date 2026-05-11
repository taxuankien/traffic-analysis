import { HelpCircle } from 'lucide-react';

interface Props {
  label: string;
  bounds: [number, number, number, number];
  onChange: (v: [number, number, number, number]) => void;
  description?: string;
  error?: string;
}

const LABELS = ['x_min', 'y_min', 'x_max', 'y_max'];

export function BoundsInput({ label, bounds, onChange, description, error }: Props) {
  const handleChange = (idx: number, val: number) => {
    const next = [...bounds] as [number, number, number, number];
    next[idx] = val;
    onChange(next);
  };

  return (
    <div style={{ gridColumn: '1 / -1' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <label className="label" style={{ margin: 0 }}>{label}</label>
        {description && (
          <span className="tooltip-trigger">
            <HelpCircle size={13} style={{ color: 'var(--color-text-muted)' }} />
            <span className="tooltip-content">{description}</span>
          </span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        {LABELS.map((name, i) => (
          <div key={name} style={{ flex: 1 }}>
            <div style={{ fontSize: '0.6875rem', color: 'var(--color-text-muted)', marginBottom: 4 }}>
              {name}
            </div>
            <input
              className={`input ${error ? 'input-error' : ''}`}
              type="number"
              value={bounds[i]}
              min={0}
              max={1}
              step={0.01}
              onChange={(e) => handleChange(i, Number(e.target.value))}
              style={{ textAlign: 'center' }}
            />
          </div>
        ))}
      </div>
      {error && (
        <p style={{ color: 'var(--color-error)', fontSize: '0.75rem', marginTop: 4 }}>{error}</p>
      )}
    </div>
  );
}
