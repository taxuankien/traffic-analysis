import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Play, X, AlertTriangle, Info } from 'lucide-react';
import { getSource } from '../api/sources';
import { getRoi } from '../api/roi';
import { startSession, cancelSession } from '../api/sessions';
import { useSessionProgress } from '../hooks/useSessionProgress';
import { ProgressBar } from '../components/ProgressBar';
import { IntervalTable } from '../components/IntervalTable';
import { useToast } from '../components/Toast';


export default function AnalysisPage() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: source } = useQuery({ queryKey: ['source', sourceId], queryFn: () => getSource(sourceId!), enabled: !!sourceId });
  const { data: roi } = useQuery({ queryKey: ['roi', sourceId], queryFn: () => getRoi(sourceId!), enabled: !!sourceId });

  const [interval, setInterval_] = useState(30);
  const [renderVideo, setRenderVideo] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const progress = useSessionProgress(sessionId);
  const isRunning = sessionId && (progress.status === 'running' || progress.status === 'connecting');
  const pct = progress.totalFrames > 0 ? (progress.processedFrames / progress.totalFrames) * 100 : 0;


  const handleStart = async () => {
    if (!sourceId) return;
    setStarting(true);
    try {
      const session = await startSession(sourceId, interval, renderVideo);
      setSessionId(session.id);
      toast('info', `Phiên ${session.id} đã bắt đầu`);
    } catch (err: unknown) {
      toast('error', err instanceof Error ? err.message : 'Không thể bắt đầu phân tích');
    }
    setStarting(false);
  };

  const handleCancel = async () => {
    if (!sessionId) return;
    try {
      await cancelSession(sessionId);
      toast('info', 'Đang huỷ phiên...');
    } catch (err: unknown) {
      toast('error', err instanceof Error ? err.message : 'Huỷ thất bại');
    }
  };

  const noRoi = roi === null;

  return (
    <div className="animate-fade-in" style={{ padding: 32, maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <Link to="/sources" className="btn btn-ghost btn-icon"><ArrowLeft size={18} /></Link>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Phân tích: {source?.name || '...'}</h1>
      </div>

      {noRoi && (
        <div className="glass-card" style={{ padding: 20, marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12, borderColor: 'rgba(239,68,68,0.3)' }}>
          <AlertTriangle size={20} style={{ color: 'var(--color-error)' }} />
          <div>
            <p style={{ fontWeight: 500, color: 'var(--color-error)' }}>Cần cấu hình ROI trước</p>
            <Link to={`/sources/${sourceId}/roi`} style={{ color: 'var(--color-accent)', fontSize: '0.875rem' }}>
              → Cấu hình ROI
            </Link>
          </div>
        </div>
      )}

      {!isRunning && progress.status !== 'completed' && (
        <div className="glass-card" style={{ padding: 24, marginBottom: 24 }}>
          <div style={{ display: 'flex', gap: 20, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div>
              <label className="label">Interval (giây)</label>
              <input className="input" type="number" value={interval} onChange={(e) => setInterval_(Number(e.target.value))} min={5} step={5} style={{ width: 100 }} />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.875rem' }}>
              <input type="checkbox" checked={renderVideo} onChange={(e) => setRenderVideo(e.target.checked)} />
              Render annotated video (.mp4)
              <span className="tooltip-trigger">
                <Info size={14} style={{ color: 'var(--color-text-muted)' }} />
                <span className="tooltip-content">Tăng thời gian ~1.5–2× nhưng cho phép tải video annotated sau khi xong.</span>
              </span>
            </label>
            <button className="btn btn-primary" onClick={handleStart} disabled={noRoi || starting}>
              <Play size={16} /> {starting ? 'Đang bắt đầu...' : 'Bắt đầu phân tích'}
            </button>
          </div>
        </div>
      )}

      {sessionId && (
        <div className="glass-card" style={{ padding: 24, marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ fontWeight: 600 }}>
              {progress.status === 'running' && '🔄 Đang chạy'}
              {progress.status === 'connecting' && '⏳ Đang kết nối...'}
              {progress.status === 'completed' && '✅ Hoàn thành'}
              {progress.status === 'failed' && '❌ Thất bại'}
              {progress.status === 'cancelled' && '⏹ Đã huỷ'}
              : {sessionId}
            </h3>
            {isRunning && (
              <button className="btn btn-danger btn-sm" onClick={handleCancel}>
                <X size={14} /> Huỷ
              </button>
            )}
          </div>

          {(isRunning || progress.status === 'completed') && (
            <>
              <ProgressBar value={pct} label={`${progress.processedFrames.toLocaleString()} / ${progress.totalFrames.toLocaleString()} frames — ${pct.toFixed(1)}%`} />
              <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                <span>Interval: {progress.currentInterval}</span>
              </div>
            </>
          )}

          {progress.status === 'failed' && progress.error && (
            <p style={{ color: 'var(--color-error)', marginTop: 8, fontSize: '0.875rem' }}>{progress.error}</p>
          )}

          {progress.status === 'completed' && (
            <div style={{ marginTop: 16 }}>
              <button className="btn btn-primary" onClick={() => navigate(`/sources/${sourceId}/results`)}>
                📊 Xem & tải kết quả →
              </button>
            </div>
          )}
        </div>
      )}

      {progress.intervals.length > 0 && (
        <div>
          <h3 style={{ fontWeight: 600, marginBottom: 12 }}>Intervals ({progress.intervals.length})</h3>
          <IntervalTable intervals={progress.intervals} />
        </div>
      )}
    </div>
  );
}
