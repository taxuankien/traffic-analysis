import { useState, useEffect } from 'react';
import { Save, RotateCcw, X, AlertCircle, RefreshCw } from 'lucide-react';
import { useInferenceConfig } from '../hooks/useInferenceConfig';
import { type InferenceConfig } from '../api/inference';
import { ConfigSection } from '../components/config-form/ConfigSection';
import { NumberInput } from '../components/config-form/NumberInput';
import { SelectInput } from '../components/config-form/SelectInput';
import { CheckboxInput } from '../components/config-form/CheckboxInput';
import { BoundsInput } from '../components/config-form/BoundsInput';
import { ChipsInput } from '../components/config-form/ChipsInput';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToast } from '../components/Toast';

export default function InferenceSettingsPage() {
  const { config, schema, models, isLoading, save, reset, refetchModels } = useInferenceConfig();
  const { toast } = useToast();
  const [form, setForm] = useState<InferenceConfig | null>(null);
  const [dirty, setDirty] = useState(false);
  const [showReset, setShowReset] = useState(false);

  useEffect(() => {
    if (config && !form) setForm(structuredClone(config));
  }, [config, form]);

  // Block navigation when dirty
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);

  if (isLoading || !form) {
    return (
      <div style={{ padding: 32, maxWidth: 900, margin: '0 auto' }}>
        <div className="skeleton" style={{ height: 40, width: 300, marginBottom: 24 }} />
        {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 120, marginBottom: 16 }} />)}
      </div>
    );
  }

  const update = <K extends keyof InferenceConfig>(section: K, field: string, value: unknown) => {
    setForm(prev => {
      if (!prev) return prev;
      const next = structuredClone(prev);
      (next[section] as Record<string, unknown>)[field] = value;
      return next;
    });
    setDirty(true);
  };

  const handleSave = async () => {
    if (!form) return;
    try {
      await save.mutateAsync(form);
      setDirty(false);
      toast('success', 'Cấu hình đã được lưu');
    } catch (err: unknown) {
      toast('error', err instanceof Error ? err.message : 'Lưu thất bại');
    }
  };

  const handleReset = async () => {
    try {
      const result = await reset.mutateAsync();
      setForm(structuredClone(result));
      setDirty(false);
      setShowReset(false);
      toast('success', 'Đã khôi phục mặc định');
    } catch (err: unknown) {
      toast('error', err instanceof Error ? err.message : 'Reset thất bại');
    }
  };

  const handleCancel = () => {
    if (config) {
      setForm(structuredClone(config));
      setDirty(false);
    }
  };

  const modelOptions = models?.map(m => ({ value: m.name, label: `${m.name} (${m.size_mb.toFixed(1)} MB)` })) || [];
  const deviceOptions = [
    { value: '', label: 'Auto' },
    { value: 'cpu', label: 'CPU' },
    { value: 'cuda', label: 'CUDA' },
    { value: 'cuda:0', label: 'CUDA:0' },
    { value: 'mps', label: 'MPS (Apple)' },
  ];

  const s = schema || {};
  const desc = (key: string) => s[key]?.description || '';

  return (
    <div className="animate-fade-in" style={{ padding: 32, maxWidth: 900, margin: '0 auto' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Inference Settings</h1>
        <div style={{ marginTop: 8, padding: '10px 16px', background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.2)', borderRadius: 'var(--radius-md)', fontSize: '0.8125rem', color: 'var(--color-info)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertCircle size={16} />
          Thay đổi sẽ áp dụng cho phiên phân tích bắt đầu sau khi lưu. Phiên đang chạy không bị ảnh hưởng.
        </div>
      </div>

      <div className="glass-card" style={{ padding: 0, overflow: 'hidden', marginBottom: 80 }}>
        <ConfigSection title="Model">
          <SelectInput label="Weights" value={form.model.weights} onChange={(v) => update('model', 'weights', v)} options={modelOptions.length ? modelOptions : [{ value: form.model.weights, label: form.model.weights }]} description={desc('model.weights')} />
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4 }}>
            <div style={{ flex: 1 }}>
              <SelectInput label="Device" value={form.model.device || ''} onChange={(v) => update('model', 'device', v || null)} options={deviceOptions} description={desc('model.device')} />
            </div>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={refetchModels} title="Rescan models"><RefreshCw size={14} /></button>
          </div>
          <NumberInput label="Image size" value={form.model.imgsz} onChange={(v) => update('model', 'imgsz', v)} min={320} max={1920} step={32} description={desc('model.imgsz')} integer />
          <CheckboxInput label="Half precision (FP16)" checked={form.model.half} onChange={(v) => update('model', 'half', v)} description={desc('model.half')} />
          <NumberInput label="Max detections" value={form.model.max_det} onChange={(v) => update('model', 'max_det', v)} min={1} max={10000} step={1} description={desc('model.max_det')} integer />
          <CheckboxInput label="Agnostic NMS" checked={form.model.agnostic_nms} onChange={(v) => update('model', 'agnostic_nms', v)} description={desc('model.agnostic_nms')} />
        </ConfigSection>

        <ConfigSection title="Detection">
          <NumberInput label="Confidence" value={form.detection.confidence} onChange={(v) => update('detection', 'confidence', v)} min={0} max={1} step={0.01} description={desc('detection.confidence')} />
          <NumberInput label="IoU (NMS)" value={form.detection.iou} onChange={(v) => update('detection', 'iou', v)} min={0} max={1} step={0.05} description={desc('detection.iou')} />
          <ChipsInput label="COCO Class IDs" selected={form.detection.class_ids} onChange={(v) => { setForm(prev => prev ? { ...prev, detection: { ...prev.detection, class_ids: v } } : prev); setDirty(true); }} description={desc('detection.class_ids')} />
        </ConfigSection>

        <ConfigSection title="Detection ROI">
          <CheckboxInput label="Enabled" checked={form.detection_roi.enabled} onChange={(v) => update('detection_roi', 'enabled', v)} description={desc('detection_roi.enabled')} />
          <BoundsInput label="Bounds [x_min, y_min, x_max, y_max]" bounds={form.detection_roi.bounds} onChange={(v) => { setForm(prev => prev ? { ...prev, detection_roi: { ...prev.detection_roi, bounds: v } } : prev); setDirty(true); }} description={desc('detection_roi.bounds')} />
        </ConfigSection>

        <ConfigSection title="Tracking">
          <NumberInput label="Activation threshold" value={form.tracking.track_activation_threshold} onChange={(v) => update('tracking', 'track_activation_threshold', v)} min={0} max={1} step={0.05} description={desc('tracking.track_activation_threshold')} />
          <NumberInput label="Lost track buffer" value={form.tracking.lost_track_buffer} onChange={(v) => update('tracking', 'lost_track_buffer', v)} min={0} max={120} step={1} description={desc('tracking.lost_track_buffer')} integer />
          <NumberInput label="Min matching" value={form.tracking.minimum_matching_threshold} onChange={(v) => update('tracking', 'minimum_matching_threshold', v)} min={0} max={1} step={0.05} description={desc('tracking.minimum_matching_threshold')} />
          <NumberInput label="Min consecutive" value={form.tracking.minimum_consecutive_frames} onChange={(v) => update('tracking', 'minimum_consecutive_frames', v)} min={1} max={10} step={1} description={desc('tracking.minimum_consecutive_frames')} integer />
        </ConfigSection>

        <ConfigSection title="Speed">
          <NumberInput label="Min frames" value={form.speed.min_frames} onChange={(v) => update('speed', 'min_frames', v)} min={1} max={30} step={1} description={desc('speed.min_frames')} integer />
        </ConfigSection>

        <ConfigSection title="Analysis">
          <NumberInput label="Default interval (s)" value={form.analysis.default_interval_seconds} onChange={(v) => update('analysis', 'default_interval_seconds', v)} min={1} max={300} step={1} description={desc('analysis.default_interval_seconds')} />
          <NumberInput label="Frame skip" value={form.analysis.frame_skip} onChange={(v) => update('analysis', 'frame_skip', v)} min={1} max={10} step={1} description={desc('analysis.frame_skip')} integer />
        </ConfigSection>

        <ConfigSection title="Queue">
          <NumberInput label="Stopped speed (km/h)" value={form.queue.stopped_speed_kmh} onChange={(v) => update('queue', 'stopped_speed_kmh', v)} min={0.1} max={20} step={0.5} description={desc('queue.stopped_speed_kmh')} />
          <NumberInput label="Window frames" value={form.queue.window_frames} onChange={(v) => update('queue', 'window_frames', v)} min={2} max={30} step={1} description={desc('queue.window_frames')} integer />
        </ConfigSection>

        <ConfigSection title="Vehicle PCE">
          <NumberInput label="Car" value={form.vehicle_pce.car} onChange={(v) => update('vehicle_pce', 'car', v)} min={0.01} max={5} step={0.05} description={desc('vehicle_pce.car')} />
          <NumberInput label="Motorcycle" value={form.vehicle_pce.motorcycle} onChange={(v) => update('vehicle_pce', 'motorcycle', v)} min={0.01} max={2} step={0.05} description={desc('vehicle_pce.motorcycle')} />
          <NumberInput label="Bus" value={form.vehicle_pce.bus} onChange={(v) => update('vehicle_pce', 'bus', v)} min={0.01} max={10} step={0.1} description={desc('vehicle_pce.bus')} />
          <NumberInput label="Truck" value={form.vehicle_pce.truck} onChange={(v) => update('vehicle_pce', 'truck', v)} min={0.01} max={10} step={0.1} description={desc('vehicle_pce.truck')} />
        </ConfigSection>
      </div>

      {/* Sticky save bar */}
      <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, padding: '12px 32px', background: 'rgba(15,23,42,0.95)', backdropFilter: 'blur(12px)', borderTop: '1px solid var(--color-border)', display: 'flex', justifyContent: 'flex-end', gap: 12, zIndex: 40 }}>
        <button className="btn btn-secondary" onClick={handleCancel} disabled={!dirty}><X size={14} /> Huỷ thay đổi</button>
        <button className="btn btn-danger btn-sm" onClick={() => setShowReset(true)}><RotateCcw size={14} /> Khôi phục mặc định</button>
        <button className="btn btn-primary" onClick={handleSave} disabled={!dirty || save.isPending}><Save size={14} /> {save.isPending ? 'Đang lưu...' : 'Lưu'}</button>
      </div>

      <ConfirmDialog open={showReset} title="Khôi phục mặc định" message="Tất cả cấu hình inference sẽ trở về giá trị mặc định. Bạn chắc chắn?" confirmLabel="Khôi phục" danger onConfirm={handleReset} onCancel={() => setShowReset(false)} />
    </div>
  );
}
