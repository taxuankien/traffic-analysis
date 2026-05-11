import { useState, useEffect, useRef, useCallback } from 'react';
import { WS_BASE } from '../lib/constants';
import type { AnalysisInterval } from '../api/sessions';

export interface ProgressState {
  connected: boolean;
  processedFrames: number;
  totalFrames: number;
  currentInterval: number;
  status: 'connecting' | 'running' | 'completed' | 'failed' | 'cancelled';
  error: string | null;
  intervals: AnalysisInterval[];
  artifacts: { kind: string; url: string }[];
}

const INITIAL: ProgressState = {
  connected: false,
  processedFrames: 0,
  totalFrames: 0,
  currentInterval: 0,
  status: 'connecting',
  error: null,
  intervals: [],
  artifacts: [],
};

export function useSessionProgress(sessionId: string | null): ProgressState {
  const [state, setState] = useState<ProgressState>(INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);

  const connect = useCallback(() => {
    if (!sessionId) return;

    const ws = new WebSocket(`${WS_BASE}/ws/sessions/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setState((s) => ({ ...s, connected: true, status: s.status === 'connecting' ? 'running' : s.status }));
      retryRef.current = 0;
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        setState((prev) => {
          switch (msg.type) {
            case 'progress':
              return {
                ...prev,
                processedFrames: msg.processed_frames,
                totalFrames: msg.total_frames,
                currentInterval: msg.current_interval,
                status: 'running',
              };
            case 'interval':
              return {
                ...prev,
                intervals: [...prev.intervals, msg.data],
              };
            case 'completed':
              return { ...prev, status: 'completed' };
            case 'failed':
              return { ...prev, status: 'failed', error: msg.error ?? 'Unknown error' };
            case 'cancelled':
              return { ...prev, status: 'cancelled' };
            case 'artifact_ready':
              return {
                ...prev,
                artifacts: [...prev.artifacts, { kind: msg.kind, url: msg.url }],
              };
            default:
              return prev;
          }
        });
      } catch {
        // ignore malformed
      }
    };

    ws.onclose = () => {
      setState((s) => ({ ...s, connected: false }));
      // Reconnect with backoff (max 3 retries)
      if (retryRef.current < 3) {
        retryRef.current += 1;
        setTimeout(connect, 1000 * retryRef.current);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [sessionId]);

  useEffect(() => {
    setState(INITIAL);
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return state;
}
