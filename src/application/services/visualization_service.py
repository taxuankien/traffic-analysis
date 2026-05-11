"""Time-slice preview + full-video annotated rendering.

Mirrors the look-and-feel of ``script.py`` / ``result.mp4``:
- Bounding boxes, per-frame class label, tracker_id, confidence
- Trace per track
- Counting line with running ``in:N out:N`` overlay
- ROI polygon outline (the analysis area)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import supervision as sv

from src.adapters.output.video.frame_annotator import FrameAnnotator
from src.application.ports.input.visualization_port import (
    FrameDetectionView,
    RenderProgress,
    RenderProgressCallback,
    VisualizationPort,
)
from src.application.ports.output.detector_port import DetectorPort
from src.application.ports.output.repository_port import (
    ROIConfigRepositoryPort,
    SourceRepositoryPort,
)
from src.application.ports.output.tracker_port import TrackerPort
from src.application.ports.output.video_reader_port import VideoReaderPort
from src.application.services.analysis_engine import (
    build_line_counters,
    build_occupancy_zones,
)
from src.domain.entities.roi_config import ROIConfig
from src.domain.exceptions import ROIConfigNotFoundError
from src.domain.value_objects.vehicle_type import COCO_TO_VEHICLE_TYPE


class VisualizationService(VisualizationPort):
    def __init__(
        self,
        source_repo: SourceRepositoryPort,
        roi_repo: ROIConfigRepositoryPort,
        video_reader: VideoReaderPort,
        detector: DetectorPort,
        tracker: TrackerPort,
        progress_throttle_seconds: float = 0.5,
    ) -> None:
        self._sources = source_repo
        self._rois = roi_repo
        self._video = video_reader
        self._detector = detector
        self._tracker = tracker
        self._throttle = progress_throttle_seconds

    # --- Time-slice preview --------------------------------------------------

    def preview_slice(
        self,
        source_id: str,
        start_frame: int,
        end_frame: int,
    ) -> list[FrameDetectionView]:
        if end_frame <= start_frame:
            raise ValueError("end_frame must be > start_frame")
        source = self._sources.get(source_id)
        meta = self._video.get_metadata(source.path)
        end_frame = min(end_frame, meta.total_frames or end_frame)

        roi = self._safe_load_roi(source_id)
        line_counters = build_line_counters(roi) if roi else []
        occupancy_zones = (
            build_occupancy_zones(roi, (meta.width, meta.height)) if roi else []
        )
        annotator = FrameAnnotator(class_names=getattr(self._detector, "class_names", {}) or {})

        line_annot = sv.LineZoneAnnotator(thickness=2, text_thickness=2, text_scale=0.8)
        poly_annots = [
            (z.zone, sv.PolygonZoneAnnotator(zone=z.zone, color=sv.Color.RED, thickness=2))
            for z in occupancy_zones
        ]

        self._apply_per_source_roi(roi)

        # The tracker is stateful — reset so the slice starts with a clean state, but we still
        # need to feed frames from frame 0 up to ``start_frame`` for the tracker to warm up if
        # ``start_frame > 0``. Otherwise tracker_ids in the slice would not match what would
        # appear in a full-video run from the same point.
        self._tracker.reset()
        warmup_count = 0

        out: list[FrameDetectionView] = []
        try:
            for idx, frame in enumerate(self._video.iter_frames(source.path)):
                if idx >= end_frame:
                    break

                detection = self._detector.detect(frame)
                detection = self._tracker.update(detection)

                if idx < start_frame:
                    # update line counters silently so their state is consistent if the user expands the slice
                    for c in line_counters:
                        c.update(detection.raw)
                    warmup_count += 1
                    continue

                for c in line_counters:
                    c.update(detection.raw)

                line_pairs = [(c.zone, line_annot) for c in line_counters]
                annotated = annotator.annotate(
                    frame,
                    detection.raw,
                    line_zones=line_pairs,
                    polygon_zones=poly_annots,
                )
                annotated = self._draw_roi_polygons(annotated, roi)
                annotated = self._draw_counter_text(annotated, line_counters)

                out.append(
                    FrameDetectionView(
                        frame_index=idx,
                        frame=annotated,
                        detections=self._extract_detections(detection.raw),
                    )
                )
            return out
        finally:
            self._reset_per_source_roi()

    # --- Full-video render ---------------------------------------------------

    def render_full_video(
        self,
        source_id: str,
        target_path: str,
        progress_cb: RenderProgressCallback | None = None,
    ) -> str:
        source = self._sources.get(source_id)
        meta = self._video.get_metadata(source.path)
        roi = self._safe_load_roi(source_id)

        line_counters = build_line_counters(roi) if roi else []
        occupancy_zones = (
            build_occupancy_zones(roi, (meta.width, meta.height)) if roi else []
        )

        annotator = FrameAnnotator(class_names=getattr(self._detector, "class_names", {}) or {})
        line_annot = sv.LineZoneAnnotator(thickness=2, text_thickness=2, text_scale=0.8)
        poly_annots = [
            (z.zone, sv.PolygonZoneAnnotator(zone=z.zone, color=sv.Color.RED, thickness=2))
            for z in occupancy_zones
        ]

        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        video_info = sv.VideoInfo(
            width=meta.width,
            height=meta.height,
            fps=int(round(meta.fps)) or 30,
            total_frames=meta.total_frames,
        )

        self._apply_per_source_roi(roi)
        self._tracker.reset()

        last_emit = 0.0
        frame_idx = 0
        try:
            with sv.VideoSink(target_path=str(target), video_info=video_info) as sink:
                for frame in self._video.iter_frames(source.path):
                    detection = self._detector.detect(frame)
                    detection = self._tracker.update(detection)
                    for c in line_counters:
                        c.update(detection.raw)

                    line_pairs = [(c.zone, line_annot) for c in line_counters]
                    annotated = annotator.annotate(
                        frame,
                        detection.raw,
                        line_zones=line_pairs,
                        polygon_zones=poly_annots,
                    )
                    annotated = self._draw_roi_polygons(annotated, roi)
                    annotated = self._draw_counter_text(annotated, line_counters)
                    sink.write_frame(annotated)

                    frame_idx += 1
                    if progress_cb is not None:
                        now = time.monotonic()
                        if now - last_emit >= self._throttle:
                            progress_cb(
                                RenderProgress(
                                    current_frame=frame_idx,
                                    total_frames=meta.total_frames,
                                )
                            )
                            last_emit = now

            if progress_cb is not None:
                progress_cb(RenderProgress(current_frame=frame_idx, total_frames=meta.total_frames))
            return str(target)
        finally:
            self._reset_per_source_roi()

    # --- Helpers -------------------------------------------------------------

    def _safe_load_roi(self, source_id: str) -> ROIConfig | None:
        try:
            return self._rois.load(source_id)
        except ROIConfigNotFoundError:
            return None

    def _apply_per_source_roi(self, roi: ROIConfig | None) -> None:
        if hasattr(self._detector, "set_roi_bounds"):
            self._detector.set_roi_bounds(roi.detection_roi if roi else None)

    def _reset_per_source_roi(self) -> None:
        if hasattr(self._detector, "set_roi_bounds"):
            self._detector.set_roi_bounds(None)

    @staticmethod
    def _draw_roi_polygons(frame: np.ndarray, roi: ROIConfig | None) -> np.ndarray:
        if roi is None:
            return frame
        out = frame
        for poly in roi.roi_polygons:
            pts = np.array(poly.points, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], isClosed=True, color=(0, 0, 255), thickness=2)
            # Translucent fill
            overlay = out.copy()
            cv2.fillPoly(overlay, [pts], color=(0, 0, 255))
            out = cv2.addWeighted(overlay, 0.10, out, 0.90, 0)
            # Label
            cx = int(np.mean([p[0] for p in poly.points]))
            cy = int(np.mean([p[1] for p in poly.points]))
            cv2.putText(
                out, poly.name, (cx, cy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
            )
        return out

    @staticmethod
    def _draw_counter_text(frame: np.ndarray, line_counters) -> np.ndarray:
        if not line_counters:
            return frame
        out = frame
        y = 30
        for c in line_counters:
            in_total = sum(c.counts_in.values())
            out_total = sum(c.counts_out.values())
            line = f"{c.line.name}  IN: {in_total}  OUT: {out_total}"
            cv2.putText(out, line, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(out, line, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
            y += 26
            for cls in sorted(set(c.counts_in) | set(c.counts_out)):
                cnt_in = c.counts_in.get(cls, 0)
                cnt_out = c.counts_out.get(cls, 0)
                detail = f"  {cls}: in={cnt_in} out={cnt_out}"
                cv2.putText(out, detail, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(out, detail, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
                y += 22
            y += 4
        return out

    @staticmethod
    def _extract_detections(raw: Any) -> list[dict]:
        out: list[dict] = []
        if raw is None or len(raw) == 0:
            return out
        xyxy = raw.xyxy
        cids = raw.class_id if raw.class_id is not None else [None] * len(raw)
        confs = raw.confidence if raw.confidence is not None else [None] * len(raw)
        tids = raw.tracker_id if raw.tracker_id is not None else [None] * len(raw)
        for i in range(len(raw)):
            cid = int(cids[i]) if cids[i] is not None else None
            cls_name = COCO_TO_VEHICLE_TYPE[cid].name if cid in COCO_TO_VEHICLE_TYPE else None
            out.append({
                "tracker_id": int(tids[i]) if tids[i] is not None else None,
                "class_id": cid,
                "class_name": cls_name,
                "confidence": float(confs[i]) if confs[i] is not None else None,
                "bbox_xyxy": [float(v) for v in xyxy[i]],
            })
        return out
