interface Props {
  value: number; // 0-100
  animated?: boolean;
  label?: string;
}

export function ProgressBar({ value, animated = true, label }: Props) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div>
      <div className="progress-bar-track">
        <div
          className={`progress-bar-fill ${animated ? 'animated' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {label && (
        <div style={{ marginTop: 4, fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
          {label}
        </div>
      )}
    </div>
  );
}
