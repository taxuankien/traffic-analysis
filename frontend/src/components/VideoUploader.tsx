import { useRef, useState, useCallback } from 'react';
import { Upload, FileVideo } from 'lucide-react';
import { ProgressBar } from './ProgressBar';

interface Props {
  onUpload: (name: string, file: File, onProgress: (pct: number) => void) => Promise<void>;
  onClose: () => void;
}

export function VideoUploader({ onUpload, onClose }: Props) {
  const [name, setName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragover, setDragover] = useState(false);

  const handleFile = useCallback((f: File) => {
    setFile(f);
    if (!name) setName(f.name.replace(/\.[^.]+$/, ''));
    setError('');
  }, [name]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !name.trim()) return;
    setError('');
    setProgress(0);
    try {
      await onUpload(name.trim(), file, setProgress);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Upload thất bại');
      setProgress(null);
    }
  };

  const uploading = progress !== null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: 20 }}>
          <Upload size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />
          Thêm video
        </h3>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label className="label">Tên nguồn</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Cam 1 - QL1"
              disabled={uploading}
              required
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label className="label">File video</label>
            {!file ? (
              <div
                className={`drop-zone ${dragover ? 'dragover' : ''}`}
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
                onDragLeave={() => setDragover(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragover(false);
                  const f = e.dataTransfer.files[0];
                  if (f) handleFile(f);
                }}
              >
                <FileVideo size={32} style={{ color: 'var(--color-text-muted)', marginBottom: 8 }} />
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem' }}>
                  Kéo thả hoặc click để chọn file
                </p>
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginTop: 4 }}>
                  .mp4, .avi, .mov, .mkv
                </p>
              </div>
            ) : (
              <div style={{
                padding: '12px 16px',
                background: 'var(--color-bg-input)',
                borderRadius: 'var(--radius-md)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: '0.875rem',
              }}>
                <FileVideo size={16} style={{ color: 'var(--color-accent)' }} />
                <span style={{ flex: 1 }}>{file.name}</span>
                {!uploading && (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setFile(null)}>
                    Đổi
                  </button>
                )}
              </div>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".mp4,.avi,.mov,.mkv"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
              }}
            />
          </div>

          {uploading && (
            <div style={{ marginBottom: 16 }}>
              <ProgressBar value={progress} label={`${progress.toFixed(0)}%`} />
            </div>
          )}

          {error && (
            <p style={{ color: 'var(--color-error)', fontSize: '0.875rem', marginBottom: 12 }}>
              {error}
            </p>
          )}

          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={uploading}>
              Huỷ
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!file || !name.trim() || uploading}
            >
              {uploading ? 'Đang upload...' : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
