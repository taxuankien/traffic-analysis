import { VEHICLE_CLASSES } from '../../lib/constants';

interface Props {
  label: string;
  selected: number[];
  onChange: (ids: number[]) => void;
  description?: string;
}

export function ChipsInput({ label, selected, onChange, description }: Props) {
  const toggle = (id: number) => {
    onChange(
      selected.includes(id)
        ? selected.filter((x) => x !== id)
        : [...selected, id],
    );
  };

  return (
    <div style={{ gridColumn: '1 / -1' }}>
      <label className="label">{label}</label>
      {description && (
        <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: 8 }}>
          {description}
        </p>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {VEHICLE_CLASSES.map((vc) => {
          const active = selected.includes(vc.id);
          return (
            <button
              key={vc.id}
              type="button"
              onClick={() => toggle(vc.id)}
              style={{
                padding: '6px 14px',
                borderRadius: 9999,
                fontSize: '0.8125rem',
                fontWeight: 500,
                border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-border)'}`,
                background: active ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                color: active ? 'var(--color-accent-hover)' : 'var(--color-text-secondary)',
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
              }}
            >
              {active ? '✓ ' : ''}{vc.name} ({vc.id})
            </button>
          );
        })}
      </div>
    </div>
  );
}
