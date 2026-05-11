import { FileText, Film, BarChart3, MapPin, Package, Download } from 'lucide-react';
import type { Artifact } from '../api/artifacts';
import { downloadUrl, bundleUrl } from '../api/artifacts';
import { formatBytes } from '../lib/utils';
import { triggerDownload } from '../lib/download';

interface Props {
  artifacts: Artifact[];
  sessionId: string;
  onPreviewVideo?: (url: string) => void;
  renderingVideo?: boolean;
  onRequestRender?: () => void;
  sessionCompleted: boolean;
}

const ICONS: Record<string, typeof FileText> = {
  csv: FileText,
  video: Film,
  summary: BarChart3,
  roi: MapPin,
};

export function ArtifactList({
  artifacts,
  sessionId,
  onPreviewVideo,
  renderingVideo,
  onRequestRender,
  sessionCompleted,
}: Props) {
  if (!sessionCompleted) {
    return (
      <div className="glass-card" style={{ padding: 20, textAlign: 'center' }}>
        <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
          Phiên chưa hoàn tất, không có kết quả tải về.
        </p>
      </div>
    );
  }

  const hasVideo = artifacts.some((a) => a.kind === 'video');

  return (
    <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div
        style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--color-border)',
          fontWeight: 600,
          fontSize: '0.9375rem',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <Download size={16} style={{ color: 'var(--color-accent)' }} />
        Tải kết quả
      </div>

      <div style={{ padding: '8px 0' }}>
        {artifacts.map((a) => {
          const Icon = ICONS[a.kind] || FileText;
          return (
            <div
              key={a.name}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '10px 20px',
                fontSize: '0.875rem',
                transition: 'background var(--transition-fast)',
              }}
            >
              <Icon size={16} style={{ color: 'var(--color-accent)', flexShrink: 0 }} />
              <span style={{ flex: 1 }}>{a.name}</span>
              <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                {formatBytes(a.size_bytes)}
              </span>
              {a.kind === 'video' && onPreviewVideo && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => onPreviewVideo(a.preview_url || a.download_url)}
                >
                  ▶ Xem
                </button>
              )}
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => triggerDownload(downloadUrl(a.download_url), a.name)}
              >
                ⬇ Tải
              </button>
            </div>
          );
        })}

        {!hasVideo && !renderingVideo && sessionCompleted && onRequestRender && (
          <div style={{ padding: '10px 20px' }}>
            <button className="btn btn-secondary btn-sm" onClick={onRequestRender}>
              🎬 Tạo video annotated
            </button>
          </div>
        )}

        {renderingVideo && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 20px',
              fontSize: '0.875rem',
              color: 'var(--color-text-muted)',
            }}
          >
            <Film size={16} />
            <span>🎬 annotated.mp4 — ⏳ Đang render...</span>
          </div>
        )}
      </div>

      <div
        style={{
          padding: '12px 20px',
          borderTop: '1px solid var(--color-border)',
        }}
      >
        <button
          className="btn btn-primary btn-sm"
          onClick={() =>
            triggerDownload(
              bundleUrl(sessionId),
              `results_${sessionId}_bundle.zip`,
            )
          }
        >
          <Package size={14} />
          Tải tất cả (ZIP)
        </button>
      </div>
    </div>
  );
}
