import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import { getSource } from '../api/sources';
import { listSessions, listIntervals, type AnalysisInterval } from '../api/sessions';
import { listArtifacts, requestRenderVideo, type Artifact } from '../api/artifacts';
import { IntervalTable } from '../components/IntervalTable';
import { ArtifactList } from '../components/ArtifactList';
import { VideoPreview } from '../components/VideoPreview';
import { useToast } from '../components/Toast';
import { formatPercent } from '../lib/utils';

export default function ResultsPage() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const { toast } = useToast();

  const { data: source } = useQuery({ queryKey: ['source', sourceId], queryFn: () => getSource(sourceId!), enabled: !!sourceId });
  const { data: sessions } = useQuery({ queryKey: ['sessions', sourceId], queryFn: () => listSessions(sourceId!), enabled: !!sourceId });

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [intervals, setIntervals] = useState<AnalysisInterval[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [renderingVideo, setRenderingVideo] = useState(false);

  const selectedSession = sessions?.find(s => s.id === selectedSessionId);
  const completed = selectedSession?.status === 'completed';

  // Auto-select first completed session
  useEffect(() => {
    if (sessions?.length && !selectedSessionId) {
      const first = sessions.find(s => s.status === 'completed') || sessions[0];
      setSelectedSessionId(first.id);
    }
  }, [sessions, selectedSessionId]);

  // Load intervals and artifacts when session changes
  useEffect(() => {
    if (!selectedSessionId) return;
    listIntervals(selectedSessionId).then(setIntervals).catch(() => {});
    listArtifacts(selectedSessionId).then(setArtifacts).catch(() => {});
  }, [selectedSessionId]);

  // Poll artifacts when rendering
  useEffect(() => {
    if (!renderingVideo || !selectedSessionId) return;
    const id = window.setInterval(() => {
      listArtifacts(selectedSessionId).then((a) => {
        setArtifacts(a);
        if (a.some(x => x.kind === 'video')) {
          setRenderingVideo(false);
          toast('success', 'Annotated video sẵn sàng');
        }
      }).catch(() => {});
    }, 5000);
    return () => window.clearInterval(id);
  }, [renderingVideo, selectedSessionId, toast]);

  // Summary computed from intervals
  const summary = intervals.length > 0 ? {
    totalCar: intervals.reduce((a, iv) => a + (iv.vehicle_counts.car || 0), 0),
    totalMoto: intervals.reduce((a, iv) => a + (iv.vehicle_counts.motorcycle || 0), 0),
    totalBus: intervals.reduce((a, iv) => a + (iv.vehicle_counts.bus || 0), 0),
    totalTruck: intervals.reduce((a, iv) => a + (iv.vehicle_counts.truck || 0), 0),
    avgOcc: intervals.reduce((a, iv) => a + iv.occupancy_ratio, 0) / intervals.length,
    avgSpeed: intervals.reduce((a, iv) => a + iv.avg_speed_kmh, 0) / intervals.length,
  } : null;

  const handleRequestRender = async () => {
    if (!selectedSessionId) return;
    try {
      await requestRenderVideo(selectedSessionId);
      setRenderingVideo(true);
      toast('info', 'Đang render annotated video...');
    } catch (err: unknown) {
      toast('error', err instanceof Error ? err.message : 'Render thất bại');
    }
  };

  return (
    <div className="animate-fade-in" style={{ padding: 32, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <Link to="/sources" className="btn btn-ghost btn-icon"><ArrowLeft size={18} /></Link>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Kết quả: {source?.name || '...'}</h1>
      </div>

      {/* Session selector */}
      <div className="glass-card" style={{ padding: 16, marginBottom: 24, display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <label className="label" style={{ margin: 0 }}>Session:</label>
        <select className="input select" value={selectedSessionId || ''} onChange={(e) => setSelectedSessionId(e.target.value)} style={{ width: 220 }}>
          {sessions?.map(s => (
            <option key={s.id} value={s.id}>{s.id} ({s.status})</option>
          ))}
        </select>
        {selectedSession && (
          <span className={`badge badge-${completed ? 'success' : selectedSession.status === 'running' ? 'warning' : selectedSession.status === 'failed' ? 'error' : 'neutral'}`}>
            {selectedSession.status}
          </span>
        )}
      </div>

      {/* Summary */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12, marginBottom: 24 }}>
          {[
            ['Intervals', intervals.length],
            ['Car', summary.totalCar],
            ['Moto', summary.totalMoto],
            ['Bus', summary.totalBus],
            ['Truck', summary.totalTruck],
            ['Avg Occ', formatPercent(summary.avgOcc)],
            ['Avg Speed', `${summary.avgSpeed.toFixed(1)} km/h`],
          ].map(([label, value]) => (
            <div key={String(label)} className="glass-card" style={{ padding: '16px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--color-accent-hover)' }}>{value}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 24 }}>
        {/* Intervals table */}
        <div>
          <h3 style={{ fontWeight: 600, marginBottom: 12 }}>Intervals</h3>
          <IntervalTable intervals={intervals} />
        </div>

        {/* Artifacts panel */}
        <div>
          <ArtifactList
            artifacts={artifacts}
            sessionId={selectedSessionId || ''}
            sessionCompleted={completed}
            renderingVideo={renderingVideo}
            onRequestRender={handleRequestRender}
            onPreviewVideo={(url) => setVideoUrl(url)}
          />
          {videoUrl && <VideoPreview url={videoUrl} onClose={() => setVideoUrl(null)} />}
        </div>
      </div>
    </div>
  );
}
