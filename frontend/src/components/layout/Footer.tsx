export function Footer() {
  return (
    <footer
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '8px 24px',
        borderTop: '1px solid var(--color-border)',
        fontSize: '0.75rem',
        color: 'var(--color-text-muted)',
        background: 'rgba(15, 23, 42, 0.5)',
        gap: 16,
      }}
    >
      <span>Traffic Analysis v1.0</span>
      <span>•</span>
      <a
        href="/docs"
        target="_blank"
        rel="noreferrer"
        style={{ color: 'var(--color-text-muted)', textDecoration: 'none' }}
      >
        API Docs
      </a>
    </footer>
  );
}
