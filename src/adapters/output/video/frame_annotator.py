from __future__ import annotations

from typing import Any

import numpy as np
import supervision as sv


class FrameAnnotator:
    """Compose supervision annotators for tracked detections, lines, and zones."""

    def __init__(self, class_names: dict[int, str] | None = None) -> None:
        self._class_names = class_names or {}
        # supervision >=0.20 renamed BoxAnnotator -> BoundingBoxAnnotator (with BoxAnnotator
        # remaining as a deprecated alias). Pick whichever is available.
        bbox_cls = getattr(sv, "BoundingBoxAnnotator", None) or sv.BoxAnnotator
        self._box = bbox_cls(thickness=2)
        self._label = sv.LabelAnnotator(text_thickness=1, text_scale=0.5)
        self._trace = sv.TraceAnnotator(thickness=2, trace_length=30)

    def annotate(
        self,
        frame: np.ndarray,
        detections: Any,
        line_zones: list[tuple[Any, sv.LineZoneAnnotator]] | None = None,
        polygon_zones: list[tuple[sv.PolygonZone, sv.PolygonZoneAnnotator]] | None = None,
    ) -> np.ndarray:
        out = frame.copy()
        labels = self._build_labels(detections)
        # Trace requires tracker_id — skip for stateless single-frame detections
        if getattr(detections, "tracker_id", None) is not None and len(detections) > 0:
            out = self._trace.annotate(scene=out, detections=detections)
        out = self._box.annotate(scene=out, detections=detections)
        out = self._label.annotate(scene=out, detections=detections, labels=labels)

        if line_zones:
            for line_zone, annot in line_zones:
                out = annot.annotate(out, line_counter=line_zone)
        if polygon_zones:
            for zone, annot in polygon_zones:
                out = annot.annotate(scene=out)
        return out

    def _build_labels(self, detections: Any) -> list[str]:
        labels: list[str] = []
        tracker_ids = (
            detections.tracker_id if getattr(detections, "tracker_id", None) is not None else []
        )
        confidences = (
            detections.confidence if getattr(detections, "confidence", None) is not None else []
        )
        class_ids = (
            detections.class_id if getattr(detections, "class_id", None) is not None else []
        )
        n = len(detections)
        for i in range(n):
            tid = tracker_ids[i] if i < len(tracker_ids) else None
            cid = class_ids[i] if i < len(class_ids) else None
            conf = confidences[i] if i < len(confidences) else None
            cls_name = self._class_names.get(int(cid), str(cid)) if cid is not None else "?"
            tid_str = f"#{int(tid)} " if tid is not None else ""
            conf_str = f" {conf:.2f}" if conf is not None else ""
            labels.append(f"{tid_str}{cls_name}{conf_str}")
        return labels
