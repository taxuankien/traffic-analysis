

interface Props {
  url: string;
  onClose: () => void;
}

export function VideoPreview({ url, onClose }: Props) {
  // Backend URLs already start with /api — use as-is
  const fullUrl = url;

  return (
    <div className="glass-card" style={{ padding: 16, marginTop: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>Preview Annotated Video</span>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>✕ Đóng</button>
      </div>
      <video
        src={fullUrl}
        controls
        preload="metadata"
        style={{
          width: '100%',
          maxHeight: 480,
          borderRadius: 'var(--radius-md)',
          background: '#000',
        }}
      />
    </div>
  );
}
