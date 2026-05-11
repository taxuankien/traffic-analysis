import { Link, useLocation } from 'react-router-dom';
import { Video, Settings } from 'lucide-react';
import { SystemMonitorPill } from './SystemMonitorPill';

export function TopBar() {
  const loc = useLocation();

  const linkStyle = (path: string) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 16px',
    borderRadius: 'var(--radius-md)',
    fontSize: '0.875rem',
    fontWeight: 500 as const,
    textDecoration: 'none',
    color: loc.pathname.startsWith(path) || (path === '/sources' && loc.pathname === '/')
      ? 'var(--color-accent-hover)'
      : 'var(--color-text-secondary)',
    background: loc.pathname.startsWith(path) || (path === '/sources' && loc.pathname === '/')
      ? 'rgba(99, 102, 241, 0.1)'
      : 'transparent',
    transition: 'all var(--transition-fast)',
  });

  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        height: 60,
        borderBottom: '1px solid var(--color-border)',
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(12px)',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 32 }}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 'var(--radius-sm)',
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Activity size={16} color="white" />
        </div>
        <span style={{ fontWeight: 700, fontSize: '1rem' }}>Traffic Analysis</span>
      </div>

      <nav style={{ display: 'flex', gap: 4, flex: 1 }}>
        <Link to="/sources" style={linkStyle('/sources')}>
          <Video size={16} /> Sources
        </Link>
        <Link to="/settings/inference" style={linkStyle('/settings')}>
          <Settings size={16} /> Inference Settings
        </Link>
      </nav>

      <SystemMonitorPill />
    </header>
  );
}

// Re-export for convenience
import { Activity } from 'lucide-react';
