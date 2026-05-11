import { HelpCircle } from 'lucide-react';

interface Props {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  description?: string;
  error?: string;
  integer?: boolean;
}

export function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  description,
  error,
  integer,
}: Props) {
  const handleChange = (v: number) => {
    onChange(integer ? Math.round(v) : v);
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <label className="label" style={{ margin: 0 }}>{label}</label>
        {description && (
          <span className="tooltip-trigger">
            <HelpCircle size={13} style={{ color: 'var(--color-text-muted)' }} />
            <span className="tooltip-content">{description}</span>
          </span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {min !== undefined && max !== undefined && (
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => handleChange(Number(e.target.value))}
            style={{ flex: 1 }}
          />
        )}
        <input
          className={`input ${error ? 'input-error' : ''}`}
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => handleChange(Number(e.target.value))}
          style={{ width: 90, textAlign: 'right' }}
        />
      </div>
      {error && (
        <p style={{ color: 'var(--color-error)', fontSize: '0.75rem', marginTop: 4 }}>{error}</p>
      )}
    </div>
  );
}
