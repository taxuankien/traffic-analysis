from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import supervision as sv

from src.application.ports.input.analysis_port import AnalysisPort, AnalysisProgress
from src.application.ports.output.detector_port import DetectorPort
from src.application.ports.output.repository_port import (
    IntervalRepositoryPort,
    ROIConfigRepositoryPort,
    SessionRepositoryPort,
    SourceRepositoryPort,
)
from src.application.ports.output.tracker_port import TrackerPort
from src.application.ports.output.video_reader_port import VideoReaderPort
from src.application.services.analysis_engine import (
    IntervalAggregator,
    QueueDetector,
    SpeedEstimator,
    build_line_counters,
    build_occupancy_zones,
)
from src.domain.entities.analysis_session import AnalysisSession
from src.domain.exceptions import ROIConfigNotFoundError


ProgressCallback = Callable[[AnalysisProgress], None]
IntervalCallback = Callable[["AnalysisInterval"], None]


class CancelledError(Exception):
    """Raised internally when ``cancel_event.is_set()`` mid-run."""


class AnalysisService(AnalysisPort):
    def __init__(
        self,
        source_repo: SourceRepositoryPort,
        roi_repo: ROIConfigRepositoryPort,
        session_repo: SessionRepositoryPort,
        interval_repo: IntervalRepositoryPort,
        video_reader: VideoReaderPort,
        detector: DetectorPort,
        tracker: TrackerPort,
        progress_throttle_seconds: float = 0.5,
        speed_min_frames: int = 5,
        default_interval_seconds: float = 30.0,
        queue_speed_kmh: float = 5.0,
        queue_window_frames: int = 5,
        frame_skip: int = 1,
    ) -> None:
        self._sources = source_repo
        self._rois = roi_repo
        self._sessions = session_repo
        self._intervals = interval_repo
        self._video = video_reader
        self._detector = detector
        self._tracker = tracker
        self._throttle = progress_throttle_seconds
        self._speed_min_frames = speed_min_frames
        self._default_interval_seconds = default_interval_seconds
        self._queue_speed_kmh = queue_speed_kmh
        self._queue_window_frames = queue_window_frames
        self._frame_skip = max(1, int(frame_skip))

    def start_session(self, source_id: str, interval_seconds: float | None = None) -> AnalysisSession:
        if interval_seconds is None:
            interval_seconds = self._default_interval_seconds
        self._sources.get(source_id)
        if not self._rois.exists(source_id):
            raise ROIConfigNotFoundError(f"No ROI config for source '{source_id}'")
        session = AnalysisSession(
            id=f"sess_{uuid.uuid4().hex[:10]}",
            source_id=source_id,
            interval_seconds=interval_seconds,
        )
        self._sessions.save(session)
        return session

    def run_session(
        self,
        session_id: str,
        progress_cb: ProgressCallback | None = None,
        annotated_output_path: str | None = None,
        interval_cb: IntervalCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> AnalysisSession:
        session = self._find_session(session_id)
        source = self._sources.get(session.source_id)
        roi = self._rois.load(session.source_id)
        meta = self._video.get_metadata(source.path)

        # Update source with discovered metadata
        if source.fps != meta.fps or source.total_frames != meta.total_frames:
            source.fps = meta.fps
            source.width = meta.width
            source.height = meta.height
            source.total_frames = meta.total_frames
            self._sources.save(source)

        # Per-source detection ROI (drawn in the GUI ROI Editor) overrides the
        # YAML default for this run; pass None to revert when the run finishes
        # so other sessions in the same process see the original default.
        if hasattr(self._detector, "set_roi_bounds"):
            self._detector.set_roi_bounds(roi.detection_roi)

        line_counters = build_line_counters(roi)
        occupancy_zones = build_occupancy_zones(roi, (meta.width, meta.height))
        speed = SpeedEstimator(
            fps=meta.fps,
            pixels_per_meter=roi.pixels_per_meter,
            min_frames=self._speed_min_frames,
        )
        queue = QueueDetector(
            fps=meta.fps,
            pixels_per_meter=roi.pixels_per_meter,
            stopped_speed_kmh=self._queue_speed_kmh,
            window_frames=self._queue_window_frames,
        )
        agg = IntervalAggregator(
            interval_seconds=session.interval_seconds,
            fps=meta.fps,
            start_timestamp=datetime.now(),
        )

        annotator = None
        sink = None
        if annotated_output_path:
            from src.adapters.output.video.frame_annotator import FrameAnnotator

            class_names = getattr(self._detector, "class_names", {}) or {}
            annotator = FrameAnnotator(class_names=class_names)
            line_zone_annot = sv.LineZoneAnnotator(thickness=2, text_thickness=1, text_scale=0.6)
            polygon_zone_annot_factory = lambda zone: sv.PolygonZoneAnnotator(
                zone=zone, color=sv.Color.RED, thickness=2, text_thickness=1, text_scale=0.6
            )
            # Output video only contains processed frames; lower its declared fps by
            # the skip factor so playback duration matches the source video.
            sink_fps = max(1, int(meta.fps / self._frame_skip)) if meta.fps else 1
            sink_total = (
                meta.total_frames // self._frame_skip if meta.total_frames else meta.total_frames
            )
            video_info = sv.VideoInfo(width=meta.width, height=meta.height, fps=sink_fps, total_frames=sink_total)
            Path(annotated_output_path).parent.mkdir(parents=True, exist_ok=True)
            sink = sv.VideoSink(target_path=annotated_output_path, video_info=video_info)

        session.mark_started()
        self._sessions.save(session)
        self._tracker.reset()

        last_progress = 0.0
        frame_idx = 0
        frame_in_interval = 0
        intervals_completed = 0
        try:
            if sink is not None:
                sink.__enter__()
            for frame in self._video.iter_frames(source.path):
                if cancel_event is not None and cancel_event.is_set():
                    raise CancelledError(f"Session '{session_id}' cancelled by request.")
                # frame_skip > 1: process every Nth frame only. ``frame_idx`` and
                # ``frame_in_interval`` still increment for every source frame so
                # interval boundaries (in seconds) match the original video, and
                # SpeedEstimator/QueueDetector use absolute frame indices to keep
                # dt math correct regardless of the cadence of update() calls.
                process_this_frame = (frame_idx % self._frame_skip == 0)

                if process_this_frame:
                    detection = self._detector.detect(frame)
                    detection = self._tracker.update(detection)
                    raw = detection.raw

                    # Counting
                    for counter in line_counters:
                        in_by_class, out_by_class = counter.update(raw)
                        agg.add_line_counts(in_by_class, out_by_class)

                    # Occupancy + queue: trigger each zone once and reuse the mask.
                    in_zone_any = None
                    if occupancy_zones:
                        weights = np.array([z.area for z in occupancy_zones], dtype=float)
                        occs: list[float] = []
                        for z in occupancy_zones:
                            ratio, mask = z.occupancy(raw)
                            occs.append(ratio)
                            if mask.size:
                                in_zone_any = mask if in_zone_any is None else (in_zone_any | mask)
                        occs_arr = np.array(occs, dtype=float)
                        if weights.sum() > 0:
                            agg.add_occupancy(float((occs_arr * weights).sum() / weights.sum()))
                        else:
                            agg.add_occupancy(float(occs_arr.mean()) if len(occs_arr) else 0.0)

                    # Speed + queue: update history each frame so the rolling window stays warm.
                    speed.update(raw, frame_idx)
                    queue.update(raw, frame_idx)
                    agg.add_queue(self._count_queued(raw, in_zone_any, queue))

                    if annotator is not None and sink is not None:
                        line_pairs = [(c.zone, line_zone_annot) for c in line_counters]
                        poly_pairs = [
                            (z.zone, polygon_zone_annot_factory(z.zone)) for z in occupancy_zones
                        ]
                        annotated = annotator.annotate(
                            frame, raw, line_zones=line_pairs, polygon_zones=poly_pairs
                        )
                        sink.write_frame(annotated)

                frame_idx += 1
                frame_in_interval += 1

                if agg.is_full(frame_in_interval):
                    agg.add_speed(speed.average_speed_kmh())
                    interval = agg.flush()
                    self._intervals.append(session.source_id, session.id, interval)
                    if interval_cb is not None:
                        try:
                            interval_cb(interval)
                        except Exception:  # noqa: BLE001 — never let WS failure stop analysis
                            pass
                    speed.reset_window()
                    queue.reset()
                    frame_in_interval = 0
                    intervals_completed += 1

                if progress_cb is not None:
                    now = time.monotonic()
                    if now - last_progress >= self._throttle:
                        progress_cb(
                            AnalysisProgress(
                                session_id=session.id,
                                current_frame=frame_idx,
                                total_frames=meta.total_frames,
                                elapsed_seconds=now,
                                intervals_completed=intervals_completed,
                            )
                        )
                        last_progress = now

            # Flush any partial interval at the end
            if frame_in_interval > 0:
                agg.add_speed(speed.average_speed_kmh())
                interval = agg.flush()
                self._intervals.append(session.source_id, session.id, interval)
                if interval_cb is not None:
                    try:
                        interval_cb(interval)
                    except Exception:  # noqa: BLE001
                        pass
                intervals_completed += 1

            session.mark_completed()
            self._sessions.save(session)
            return session
        except CancelledError:
            session.mark_cancelled()
            self._sessions.save(session)
            raise
        except Exception as exc:
            session.mark_failed(str(exc))
            self._sessions.save(session)
            raise
        finally:
            if sink is not None:
                try:
                    sink.__exit__(None, None, None)
                except Exception:
                    pass
            if hasattr(self._detector, "set_roi_bounds"):
                self._detector.set_roi_bounds(None)

    @staticmethod
    def _count_queued(raw, in_zone_mask, queue: QueueDetector) -> int:
        """Count tracker_ids that are inside any ROI zone *and* have been stationary.

        Falls back to "all tracked detections" when no ROI zones are configured so
        the metric still reports something useful in that case.
        """
        if raw is None or len(raw) == 0 or raw.tracker_id is None:
            return 0
        n = len(raw)
        if in_zone_mask is None:
            mask = np.ones(n, dtype=bool)
        else:
            mask = in_zone_mask
        count = 0
        for i in range(n):
            if not mask[i]:
                continue
            tid = raw.tracker_id[i]
            if tid is None:
                continue
            if queue.is_queued(int(tid)):
                count += 1
        return count

    def _find_session(self, session_id: str) -> AnalysisSession:
        # Sessions are partitioned by source; we need to scan to resolve.
        for source in self._sources.list_all():
            try:
                return self._sessions.get(source.id, session_id)
            except Exception:
                continue
        raise LookupError(f"Session '{session_id}' not found in any source")
