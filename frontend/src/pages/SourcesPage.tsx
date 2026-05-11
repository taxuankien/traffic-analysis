import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus, Settings, Play, BarChart3, Trash2, Video } from 'lucide-react';
import { listSources, addSource, deleteSource, type VideoSource } from '../api/sources';
import { VideoUploader } from '../components/VideoUploader';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToast } from '../components/Toast';
import { formatTimestamp } from '../lib/utils';

export default function SourcesPage() {
  const [showUpload, setShowUpload] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<VideoSource | null>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data: sources, isLoading } = useQuery({
    queryKey: ['sources'],
    queryFn: listSources,
  });

  const handleUpload = async (name: string, file: File, onProgress: (p: number) => void) => {
    await addSource(name, file, onProgress);
    qc.invalidateQueries({ queryKey: ['sources'] });
    toast('success', 'Đã thêm nguồn video thành công');
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSource(deleteTarget.id);
      qc.invalidateQueries({ queryKey: ['sources'] });
      toast('success', `Đã xoá "${deleteTarget.name}"`);
    } catch (err: unknown) {
      toast('error', err instanceof Error ? err.message : 'Xoá thất bại');
    }
    setDeleteTarget(null);
  };

  return (
    <div className="animate-fade-in" style={{ padding: 32, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Nguồn video</h1>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginTop: 4 }}>
            Quản lý các file video đã upload để phân tích
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowUpload(true)}>
          <Plus size={16} /> Thêm video
        </button>
      </div>

      {isLoading ? (
        <div style={{ display: 'grid', gap: 12 }}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton" style={{ height: 80, borderRadius: 'var(--radius-lg)' }} />
          ))}
        </div>
      ) : !sources?.length ? (
        <div
          className="glass-card"
          style={{
            padding: 60,
            textAlign: 'center',
          }}
        >
          <Video size={48} style={{ color: 'var(--color-text-muted)', marginBottom: 16 }} />
          <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: 8 }}>Chưa có nguồn video</h3>
          <p style={{ color: 'var(--color-text-muted)', marginBottom: 20, fontSize: '0.875rem' }}>
            Upload file video để bắt đầu phân tích giao thông
          </p>
          <button className="btn btn-primary" onClick={() => setShowUpload(true)}>
            <Plus size={16} /> Thêm video đầu tiên
          </button>
        </div>
      ) : (
        <div className="table-container glass-card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Tên</th>
                <th>Thông số</th>
                <th>Tạo lúc</th>
                <th style={{ textAlign: 'right' }}>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src) => (
                <tr key={src.id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{src.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: 2 }}>
                      {src.id}
                    </div>
                  </td>
                  <td>
                    {src.metadata ? (
                      <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                        {src.metadata.width}×{src.metadata.height} • {src.metadata.fps.toFixed(0)}fps • {Math.floor(src.metadata.total_frames / src.metadata.fps)}s
                      </div>
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>—</span>
                    )}
                  </td>
                  <td style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                    {formatTimestamp(src.created_at)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                      <button
                        className="btn btn-ghost btn-icon"
                        title="Cấu hình ROI"
                        onClick={() => navigate(`/sources/${src.id}/roi`)}
                      >
                        <Settings size={16} />
                      </button>
                      <button
                        className="btn btn-ghost btn-icon"
                        title="Phân tích"
                        onClick={() => navigate(`/sources/${src.id}/analysis`)}
                      >
                        <Play size={16} />
                      </button>
                      <button
                        className="btn btn-ghost btn-icon"
                        title="Xem kết quả"
                        onClick={() => navigate(`/sources/${src.id}/results`)}
                      >
                        <BarChart3 size={16} />
                      </button>
                      <button
                        className="btn btn-ghost btn-icon"
                        title="Xoá"
                        onClick={() => setDeleteTarget(src)}
                        style={{ color: 'var(--color-error)' }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showUpload && (
        <VideoUploader onUpload={handleUpload} onClose={() => setShowUpload(false)} />
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="Xoá nguồn video"
        message={`Bạn chắc chắn muốn xoá "${deleteTarget?.name}"? File video và tất cả kết quả sẽ bị xoá.`}
        confirmLabel="Xoá"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
