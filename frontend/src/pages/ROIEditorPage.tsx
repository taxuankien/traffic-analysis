import { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Crosshair, Minus, MousePointer, Save, RotateCcw, Zap, Camera, Trash2 } from 'lucide-react';
import { getSource } from '../api/sources';
import { frameUrl, testDetect, saveFrame, type TestDetectResult } from '../api/frames';
import { getRoi, putRoi, type ROIPolygon, type CountingLine } from '../api/roi';
import { useToast } from '../components/Toast';
import { formatDuration } from '../lib/utils';

type Tool = 'polygon' | 'line' | 'select';
const POLY_COLORS = ['#6366f1', '#f59e0b', '#10b981', '#ef4444', '#3b82f6', '#ec4899'];
const LINE_COLOR = '#22d3ee';

/**
 * Compute the actual rendered rect of the image inside the container,
 * accounting for `object-fit: contain` letterboxing.
 *
 * Returns { offsetX, offsetY, renderW, renderH } — the pixel rect of
 * the visible image within the container.
 */
function getImageRenderRect(container: HTMLElement, img: HTMLImageElement | null, videoW: number, videoH: number) {
  const cw = container.clientWidth;
  const ch = container.clientHeight;

  // If we have a loaded <img>, use its naturalWidth/Height for precise aspect ratio.
  const natW = img && img.naturalWidth > 0 ? img.naturalWidth : videoW;
  const natH = img && img.naturalHeight > 0 ? img.naturalHeight : videoH;

  const containerAspect = cw / ch;
  const imageAspect = natW / natH;

  let renderW: number, renderH: number, offsetX: number, offsetY: number;
  if (imageAspect > containerAspect) {
    // Image is wider → pillarbox (bars top/bottom)
    renderW = cw;
    renderH = cw / imageAspect;
    offsetX = 0;
    offsetY = (ch - renderH) / 2;
  } else {
    // Image is taller → letterbox (bars left/right)
    renderH = ch;
    renderW = ch * imageAspect;
    offsetX = (cw - renderW) / 2;
    offsetY = 0;
  }

  return { offsetX, offsetY, renderW, renderH };
}

export default function ROIEditorPage() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const { toast } = useToast();
  const qc = useQueryClient();
  const { data: source } = useQuery({ queryKey: ['source', sourceId], queryFn: () => getSource(sourceId!), enabled: !!sourceId });
  const { data: existingRoi } = useQuery({ queryKey: ['roi', sourceId], queryFn: () => getRoi(sourceId!), enabled: !!sourceId });

  const [time, setTime] = useState(0);
  const [timeInput, setTimeInput] = useState('00:00');
  const [tool, setTool] = useState<Tool>('polygon');
  const [polygons, setPolygons] = useState<ROIPolygon[]>([]);
  const [lines, setLines] = useState<CountingLine[]>([]);
  const [pxPerMeter, setPxPerMeter] = useState('');
  const [currentPoints, setCurrentPoints] = useState<[number, number][]>([]);
  const [detectResult, setDetectResult] = useState<TestDetectResult | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [showAnnotated, setShowAnnotated] = useState(false);
  const [saving, setSaving] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  // Track the image's actual pixel dimensions from onLoad.
  // This is THE authoritative source for video resolution, since the frame
  // endpoint returns the original-resolution PNG.
  const [imgNatural, setImgNatural] = useState<{ w: number; h: number } | null>(null);

  // Priority: image naturalWidth > API metadata > fallback 1920×1080
  const videoW = imgNatural?.w || source?.metadata?.width || 1920;
  const videoH = imgNatural?.h || source?.metadata?.height || 1080;
  const totalSeconds = source?.metadata ? source.metadata.total_frames / source.metadata.fps : 300;

  useEffect(() => {
    if (existingRoi) {
      setPolygons(existingRoi.roi_polygons || []);
      setLines(existingRoi.counting_lines || []);
      if (existingRoi.pixels_per_meter) setPxPerMeter(String(existingRoi.pixels_per_meter));
    }
  }, [existingRoi]);

  const imgSrc = showAnnotated && detectResult ? detectResult.annotated_url : frameUrl(sourceId!, time);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = canvas?.parentElement;
    if (!canvas || !container) return;
    const cw = container.clientWidth;
    const ch = container.clientHeight;
    canvas.width = cw;
    canvas.height = ch;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, cw, ch);

    // Compute the exact render rect to match object-fit: contain
    const { offsetX, offsetY, renderW, renderH } = getImageRenderRect(container, imgRef.current, videoW, videoH);
    const sx = renderW / videoW;
    const sy = renderH / videoH;

    // Transform: video pixel (vx, vy) → canvas pixel (offsetX + vx*sx, offsetY + vy*sy)
    const tx = (vx: number) => offsetX + vx * sx;
    const ty = (vy: number) => offsetY + vy * sy;

    polygons.forEach((poly, i) => {
      const c = POLY_COLORS[i % POLY_COLORS.length];
      ctx.beginPath();
      poly.points.forEach(([x, y], j) => { j === 0 ? ctx.moveTo(tx(x), ty(y)) : ctx.lineTo(tx(x), ty(y)); });
      ctx.closePath(); ctx.fillStyle = c+'30'; ctx.fill(); ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.stroke();
      if (poly.points[0]) { ctx.fillStyle = c; ctx.font = '13px Inter'; ctx.fillText(poly.name, tx(poly.points[0][0])+4, ty(poly.points[0][1])-6); }
    });

    lines.forEach((l) => {
      ctx.beginPath(); ctx.moveTo(tx(l.start[0]), ty(l.start[1])); ctx.lineTo(tx(l.end[0]), ty(l.end[1]));
      ctx.strokeStyle = LINE_COLOR; ctx.lineWidth = 3; ctx.setLineDash([8,4]); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = LINE_COLOR; ctx.font = '12px Inter';
      ctx.fillText(`${l.name} (${l.direction})`, tx((l.start[0]+l.end[0])/2), ty((l.start[1]+l.end[1])/2)-8);
    });

    if (currentPoints.length > 0) {
      ctx.beginPath();
      currentPoints.forEach(([x,y], j) => { j === 0 ? ctx.moveTo(tx(x),ty(y)) : ctx.lineTo(tx(x),ty(y)); });
      ctx.strokeStyle = tool === 'polygon' ? '#fff' : LINE_COLOR; ctx.lineWidth = 2; ctx.setLineDash([4,4]); ctx.stroke(); ctx.setLineDash([]);
      currentPoints.forEach(([x,y]) => { ctx.beginPath(); ctx.arc(tx(x),ty(y),4,0,Math.PI*2); ctx.fillStyle='#fff'; ctx.fill(); });
    }
  }, [polygons, lines, currentPoints, source, tool, videoW, videoH]);

  useEffect(() => { draw(); }, [draw]);

  // Capture real image dimensions when the frame loads
  const handleImgLoad = useCallback(() => {
    const img = imgRef.current;
    if (img && img.naturalWidth > 0 && img.naturalHeight > 0) {
      setImgNatural({ w: img.naturalWidth, h: img.naturalHeight });
    }
    draw();
  }, [draw]);

  // Also redraw on window resize
  useEffect(() => {
    const onResize = () => draw();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [draw]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (tool === 'select') return;
    const canvas = canvasRef.current!;
    const container = canvas.parentElement!;
    const rect = canvas.getBoundingClientRect();

    // Compute render rect to correctly map click → video coordinates
    const { offsetX, offsetY, renderW, renderH } = getImageRenderRect(container, imgRef.current, videoW, videoH);

    // Click position relative to canvas
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;

    // Ignore clicks outside the rendered image area
    if (cx < offsetX || cx > offsetX + renderW || cy < offsetY || cy > offsetY + renderH) return;

    // Map to video pixel coordinates
    const x = Math.round((cx - offsetX) / renderW * videoW);
    const y = Math.round((cy - offsetY) / renderH * videoH);

    if (tool === 'line') {
      const pts = [...currentPoints, [x,y] as [number,number]];
      if (pts.length >= 2) {
        const name = prompt('Tên counting line:', `line_${lines.length+1}`) || `line_${lines.length+1}`;
        const dir = (prompt('Direction (in/out/both):', 'both') as 'in'|'out'|'both') || 'both';
        setLines([...lines, { name, start: pts[0], end: pts[1], direction: dir }]); setCurrentPoints([]);
      } else { setCurrentPoints(pts); }
    } else { setCurrentPoints([...currentPoints, [x,y]]); }
  };

  const handleCanvasDblClick = () => {
    if (tool !== 'polygon' || currentPoints.length < 3) return;
    const name = prompt('Tên polygon:', `lane_${polygons.length+1}`) || `lane_${polygons.length+1}`;
    setPolygons([...polygons, { name, points: [...currentPoints] }]); setCurrentPoints([]);
  };

  const handleGo = () => {
    const parts = timeInput.split(':').map(Number);
    setTime(Math.min((parts[0]||0)*60+(parts[1]||0), totalSeconds));
    setShowAnnotated(false); setDetectResult(null);
  };

  const handleSave = async () => {
    if (!sourceId) return;
    setSaving(true);
    try {
      await putRoi(sourceId, { reference_frame_index: Math.round(time*(source?.metadata?.fps||30)), roi_polygons: polygons, counting_lines: lines, pixels_per_meter: pxPerMeter ? Number(pxPerMeter) : null });
      qc.invalidateQueries({ queryKey: ['roi', sourceId] });
      toast('success', 'Đã lưu cấu hình ROI');
    } catch (err: unknown) { toast('error', err instanceof Error ? err.message : 'Lưu thất bại'); }
    setSaving(false);
  };

  return (
    <div className="animate-fade-in" style={{ padding: 24, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Link to="/sources" className="btn btn-ghost btn-icon"><ArrowLeft size={18} /></Link>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 700 }}>ROI: {source?.name || '...'}</h1>
      </div>
      <div style={{ display: 'flex', gap: 20, flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ position: 'relative', flex: 1, background: '#000', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
            <img ref={imgRef} src={imgSrc} alt="frame" onLoad={handleImgLoad} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
            <canvas ref={canvasRef} onClick={handleCanvasClick} onDoubleClick={handleCanvasDblClick} style={{ position: 'absolute', inset: 0, cursor: tool === 'select' ? 'default' : 'crosshair' }} />
          </div>
          <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
            <input type="range" min={0} max={totalSeconds} step={0.5} value={time} onChange={(e) => { const t = Number(e.target.value); setTime(t); setTimeInput(formatDuration(t)); setShowAnnotated(false); }} style={{ flex: 1 }} />
            <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)', minWidth: 80 }}>{formatDuration(time)}/{formatDuration(totalSeconds)}</span>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <input className="input" value={timeInput} onChange={(e) => setTimeInput(e.target.value)} placeholder="mm:ss" style={{ width: 90 }} onKeyDown={(e) => e.key === 'Enter' && handleGo()} />
            <button className="btn btn-secondary btn-sm" onClick={handleGo}>Go</button>
            <div style={{ flex: 1 }} />
            <button className="btn btn-secondary btn-sm" onClick={async () => { if (!sourceId) return; setDetecting(true); try { const r = await testDetect(sourceId, time); setDetectResult(r); setShowAnnotated(true); } catch {} setDetecting(false); }} disabled={detecting}>
              <Zap size={14} /> {detecting ? '...' : 'Test Detect'}
            </button>
            <button className="btn btn-secondary btn-sm" onClick={async () => { if (!sourceId) return; try { await saveFrame(sourceId, time); toast('success','Saved'); } catch {} }}>
              <Camera size={14} />
            </button>
            {showAnnotated && <button className="btn btn-ghost btn-sm" onClick={() => setShowAnnotated(false)}>Frame gốc</button>}
          </div>
          {detectResult && (
            <div className="glass-card" style={{ padding: 12, marginTop: 12, fontSize: '0.8125rem' }}>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                {Object.entries(detectResult.summary).map(([k,v]) => <span key={k} className="badge badge-info">{k}: {v}</span>)}
                <span className="badge badge-neutral">{detectResult.timings.inference_ms.toFixed(1)}ms • {detectResult.timings.device}</span>
              </div>
              {detectResult.timings.inference_ms > 100 && <p style={{ color: 'var(--color-warning)', marginTop: 8, fontSize: '0.75rem' }}>⚠ Tốc độ chậm</p>}
            </div>
          )}
        </div>
        <div className="glass-card" style={{ width: 260, padding: 20, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <h3 style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Tools</h3>
            {([['polygon','Polygon (P)',<Crosshair key="p" size={14}/>],['line','Line (L)',<Minus key="l" size={14}/>],['select','Select (V)',<MousePointer key="v" size={14}/>]] as const).map(([t,l,ic]) => (
              <button key={t} className={`btn btn-sm ${tool===t?'btn-primary':'btn-ghost'}`} onClick={() => { setTool(t); setCurrentPoints([]); }} style={{ justifyContent: 'flex-start', width: '100%', marginBottom: 4 }}>{ic} {l}</button>
            ))}
          </div>
          <div><label className="label">px/mét</label><input className="input" type="number" value={pxPerMeter} onChange={(e) => setPxPerMeter(e.target.value)} placeholder="12.5" /></div>
          <div>
            <h3 style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8, textTransform: 'uppercase' }}>Polygons ({polygons.length})</h3>
            {polygons.map((p,i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', fontSize: '0.8125rem' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: 2, background: POLY_COLORS[i%POLY_COLORS.length] }}/>{p.name}</span>
                <button className="btn btn-ghost btn-icon" onClick={() => setPolygons(polygons.filter((_,j)=>j!==i))} style={{ color: 'var(--color-error)', padding: 2 }}><Trash2 size={12}/></button>
              </div>
            ))}
          </div>
          <div>
            <h3 style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8, textTransform: 'uppercase' }}>Lines ({lines.length})</h3>
            {lines.map((l,i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', fontSize: '0.8125rem' }}>
                <span>{l.name} ({l.direction})</span>
                <button className="btn btn-ghost btn-icon" onClick={() => setLines(lines.filter((_,j)=>j!==i))} style={{ color: 'var(--color-error)', padding: 2 }}><Trash2 size={12}/></button>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 'auto', display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={handleSave} disabled={saving}><Save size={14}/> {saving ? '...' : 'Lưu'}</button>
            <button className="btn btn-secondary" onClick={() => { setPolygons(existingRoi?.roi_polygons||[]); setLines(existingRoi?.counting_lines||[]); setCurrentPoints([]); }}><RotateCcw size={14}/></button>
          </div>
        </div>
      </div>
    </div>
  );
}
