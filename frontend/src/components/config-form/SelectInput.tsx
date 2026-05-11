import { HelpCircle } from 'lucide-react';

interface Props {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  description?: string;
}

export function SelectInput({ label, value, onChange, options, description }: Props) {
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
      <select
        className="input select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}
