import { HelpCircle } from 'lucide-react';

interface Props {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  description?: string;
}

export function CheckboxInput({ label, checked, onChange, description }: Props) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <label
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          cursor: 'pointer',
          fontSize: '0.875rem',
        }}
      >
        <div
          onClick={() => onChange(!checked)}
          style={{
            width: 40,
            height: 22,
            borderRadius: 11,
            background: checked
              ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
              : 'rgba(148, 163, 184, 0.2)',
            position: 'relative',
            transition: 'background var(--transition-fast)',
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 2,
              left: checked ? 20 : 2,
              width: 18,
              height: 18,
              borderRadius: '50%',
              background: 'white',
              transition: 'left var(--transition-fast)',
              boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
            }}
          />
        </div>
        <span style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
      </label>
      {description && (
        <span className="tooltip-trigger">
          <HelpCircle size={13} style={{ color: 'var(--color-text-muted)' }} />
          <span className="tooltip-content">{description}</span>
        </span>
      )}
    </div>
  );
}
