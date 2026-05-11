from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.adapters.input.gui.image_utils import bgr_to_qpixmap
from src.bootstrap.container import Container
from src.domain.entities.roi_config import ROIConfig
from src.domain.exceptions import ROIConfigNotFoundError
from src.domain.value_objects import CountingLine, LineDirection, ROIPolygon


class Tool(Enum):
    NONE = auto()
    POLYGON = auto()
    LINE = auto()
    DETECTION_ROI = auto()


@dataclass
class _DraftPolygon:
    points: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class _DraftLine:
    start: tuple[int, int] | None = None
    end: tuple[int, int] | None = None


@dataclass
class _DraftDetectionROI:
    """First corner of the in-progress Detection ROI rectangle (pixel coords)."""

    start: tuple[int, int] | None = None


class ImageCanvas(QLabel):
    """QLabel that scales a frame and reports clicks in image coordinates."""

    point_clicked = pyqtSignal(int, int)
    point_double_clicked = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #202020;")
        self._original_pixmap: QPixmap | None = None
        self._render_rect: QRect = QRect()
        self._overlay_paint = None  # callback(painter, rect, scale)

    def set_frame(self, pixmap: QPixmap) -> None:
        self._original_pixmap = pixmap
        self._refresh()

    def set_overlay_paint(self, callback) -> None:
        self._overlay_paint = callback
        self._refresh()

    def _refresh(self) -> None:
        if self._original_pixmap is None or self._original_pixmap.isNull():
            self.setPixmap(QPixmap())
            return
        scaled = self._original_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Compose overlay onto the scaled pixmap
        composed = QPixmap(scaled.size())
        composed.fill(Qt.GlobalColor.transparent)
        painter = QPainter(composed)
        painter.drawPixmap(0, 0, scaled)
        if self._overlay_paint is not None:
            scale_x = scaled.width() / self._original_pixmap.width()
            scale_y = scaled.height() / self._original_pixmap.height()
            self._overlay_paint(painter, scaled.rect(), (scale_x, scale_y))
        painter.end()

        self.setPixmap(composed)
        # Cache where the pixmap is rendered inside the QLabel for click-mapping.
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._render_rect = QRect(x, y, scaled.width(), scaled.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _to_image_coords(self, pos: QPoint) -> tuple[int, int] | None:
        if self._original_pixmap is None or self._original_pixmap.isNull():
            return None
        if not self._render_rect.contains(pos):
            return None
        rx = pos.x() - self._render_rect.x()
        ry = pos.y() - self._render_rect.y()
        if self._render_rect.width() == 0 or self._render_rect.height() == 0:
            return None
        ix = int(rx * self._original_pixmap.width() / self._render_rect.width())
        iy = int(ry * self._original_pixmap.height() / self._render_rect.height())
        return ix, iy

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            coords = self._to_image_coords(ev.pos())
            if coords:
                self.point_clicked.emit(*coords)
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            coords = self._to_image_coords(ev.pos())
            if coords:
                self.point_double_clicked.emit(*coords)
        super().mouseDoubleClickEvent(ev)


class ROIEditorWidget(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._source_id: str | None = None
        self._frame_total = 0
        self._fps: float = 0.0

        self._tool: Tool = Tool.NONE
        self._draft_poly = _DraftPolygon()
        self._draft_line = _DraftLine()
        self._draft_det_roi = _DraftDetectionROI()
        self._polygons: list[ROIPolygon] = []
        self._lines: list[CountingLine] = []
        # Pixel-coords rectangle (x1, y1, x2, y2) for the active Detection ROI; None = unset.
        # Saved/loaded via ROIConfig.detection_roi (normalized).
        self._detection_roi_px: tuple[int, int, int, int] | None = None
        self._frame_width = 0
        self._frame_height = 0
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)

        # --- Canvas + slider ---
        left = QVBoxLayout()
        self.canvas = ImageCanvas()
        self.canvas.set_overlay_paint(self._paint_overlay)
        self.canvas.point_clicked.connect(self._on_canvas_click)
        self.canvas.point_double_clicked.connect(self._on_canvas_double_click)
        left.addWidget(self.canvas, 1)

        slider_row = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.valueChanged.connect(self._on_slider)
        self.lbl_frame = QLabel("Frame 0")
        slider_row.addWidget(QLabel("Frame:"))
        slider_row.addWidget(self.slider, 1)
        slider_row.addWidget(self.lbl_frame)
        left.addLayout(slider_row)

        # --- Time-slice picker (Luồng 1b) ---
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Frame index:"))
        self.spin_frame = QSpinBox()
        self.spin_frame.setMinimum(0)
        self.spin_frame.setMaximum(0)
        time_row.addWidget(self.spin_frame)

        time_row.addSpacing(12)
        time_row.addWidget(QLabel("Time (mm:ss[.ms] hoặc giây):"))
        self.edt_time = QLineEdit()
        self.edt_time.setPlaceholderText("vd: 1:23.5 hoặc 83.5")
        self.edt_time.setMaximumWidth(160)
        time_row.addWidget(self.edt_time)

        self.btn_goto = QPushButton("Go to Frame")
        time_row.addWidget(self.btn_goto)
        time_row.addStretch(1)
        left.addLayout(time_row)
        self.btn_goto.clicked.connect(self._on_goto_frame)

        # --- Frame test row ---
        test_row = QHBoxLayout()
        self.btn_test_detect = QPushButton("Run Test Detection")
        self.btn_save_frame = QPushButton("Save Frame as PNG")
        self.lbl_detection_summary = QLabel("Chưa có test")
        self.lbl_detection_summary.setStyleSheet("color: #555;")
        test_row.addWidget(self.btn_test_detect)
        test_row.addWidget(self.btn_save_frame)
        test_row.addWidget(self.lbl_detection_summary, 1)
        left.addLayout(test_row)
        self.btn_test_detect.clicked.connect(self._on_test_detection)
        self.btn_save_frame.clicked.connect(self._on_save_frame)

        # When the user has just run test detection, this overlay frame replaces the
        # plain frame in the canvas. Cleared next time the slider/spinbox moves.
        self._test_overlay_frame = None
        self._last_test_summary = ""

        root.addLayout(left, 3)

        # --- Side panel ---
        right = QVBoxLayout()

        tool_row = QHBoxLayout()
        self.btn_polygon = QPushButton("Vẽ polygon (double-click để đóng)")
        self.btn_polygon.setCheckable(True)
        self.btn_line = QPushButton("Vẽ counting line")
        self.btn_line.setCheckable(True)
        self.btn_clear_draft = QPushButton("Huỷ nét đang vẽ")
        tool_row.addWidget(self.btn_polygon)
        tool_row.addWidget(self.btn_line)
        right.addLayout(tool_row)
        right.addWidget(self.btn_clear_draft)

        self.btn_polygon.clicked.connect(lambda: self._set_tool(Tool.POLYGON if self.btn_polygon.isChecked() else Tool.NONE))
        self.btn_line.clicked.connect(lambda: self._set_tool(Tool.LINE if self.btn_line.isChecked() else Tool.NONE))
        self.btn_clear_draft.clicked.connect(self._cancel_draft)

        # --- Detection ROI (vùng cần detect — giảm khối lượng tính toán) ---
        right.addWidget(QLabel("Detection ROI (vùng cần detect)"))
        det_roi_row = QHBoxLayout()
        self.btn_detection_roi = QPushButton("Vẽ Detection ROI (click 2 góc)")
        self.btn_detection_roi.setCheckable(True)
        self.btn_clear_detection_roi = QPushButton("Xoá")
        det_roi_row.addWidget(self.btn_detection_roi)
        det_roi_row.addWidget(self.btn_clear_detection_roi)
        right.addLayout(det_roi_row)
        self.lbl_detection_roi = QLabel("Chưa cấu hình → dùng default từ inference.yaml")
        self.lbl_detection_roi.setStyleSheet("color: #555;")
        self.lbl_detection_roi.setWordWrap(True)
        right.addWidget(self.lbl_detection_roi)

        self.btn_detection_roi.clicked.connect(
            lambda: self._set_tool(Tool.DETECTION_ROI if self.btn_detection_roi.isChecked() else Tool.NONE)
        )
        self.btn_clear_detection_roi.clicked.connect(self._clear_detection_roi)

        right.addWidget(QLabel("ROI Polygons"))
        self.list_polygons = QListWidget()
        right.addWidget(self.list_polygons, 1)

        right.addWidget(QLabel("Counting Lines"))
        self.list_lines = QListWidget()
        right.addWidget(self.list_lines, 1)

        line_dir_row = QHBoxLayout()
        line_dir_row.addWidget(QLabel("Hướng line mới:"))
        self.cmb_direction = QComboBox()
        self.cmb_direction.addItems([d.value for d in LineDirection])
        line_dir_row.addWidget(self.cmb_direction)
        right.addLayout(line_dir_row)

        self.btn_remove_selected = QPushButton("Xoá mục đang chọn")
        right.addWidget(self.btn_remove_selected)
        self.btn_remove_selected.clicked.connect(self._remove_selected)

        form = QFormLayout()
        self.spin_ppm = QDoubleSpinBox()
        self.spin_ppm.setMinimum(0.0)
        self.spin_ppm.setMaximum(10000.0)
        self.spin_ppm.setDecimals(3)
        self.spin_ppm.setValue(0.0)
        form.addRow("pixels_per_meter:", self.spin_ppm)
        right.addLayout(form)

        action_row = QHBoxLayout()
        self.btn_save = QPushButton("Lưu config")
        self.btn_load = QPushButton("Tải config")
        self.btn_back = QPushButton("Quay lại")
        action_row.addWidget(self.btn_save)
        action_row.addWidget(self.btn_load)
        action_row.addWidget(self.btn_back)
        right.addLayout(action_row)

        self.btn_save.clicked.connect(self._save_config)
        self.btn_load.clicked.connect(self._load_config)
        self.btn_back.clicked.connect(self.back_requested.emit)

        root.addLayout(right, 2)

    # --- Public API ---
    def load_source(self, source_id: str) -> None:
        self._source_id = source_id
        self._polygons = []
        self._lines = []
        self._draft_poly = _DraftPolygon()
        self._draft_line = _DraftLine()
        self._draft_det_roi = _DraftDetectionROI()
        self._detection_roi_px = None
        self._refresh_lists()

        meta = self._container.video_reader.get_metadata(
            self._container.source_repo.get(source_id).path
        )
        self._frame_total = max(0, meta.total_frames - 1)
        self._fps = float(meta.fps or 0.0)
        self._frame_width = int(meta.width or 0)
        self._frame_height = int(meta.height or 0)

        try:
            cfg = self._container.roi_config_service().load_config(source_id)
            self._polygons = list(cfg.roi_polygons)
            self._lines = list(cfg.counting_lines)
            self.spin_ppm.setValue(cfg.pixels_per_meter)
            self._detection_roi_px = self._normalized_to_pixels(cfg.detection_roi)
            self._refresh_lists()
        except ROIConfigNotFoundError:
            pass
        self._refresh_detection_roi_label()

        self.slider.setMaximum(self._frame_total)
        self.slider.setValue(0)
        self.spin_frame.blockSignals(True)
        self.spin_frame.setMaximum(self._frame_total)
        self.spin_frame.setValue(0)
        self.spin_frame.blockSignals(False)
        self._update_frame(0)

    def _normalized_to_pixels(
        self, bounds: tuple[float, float, float, float] | None
    ) -> tuple[int, int, int, int] | None:
        if bounds is None or self._frame_width <= 0 or self._frame_height <= 0:
            return None
        x1, y1, x2, y2 = bounds
        return (
            int(round(x1 * self._frame_width)),
            int(round(y1 * self._frame_height)),
            int(round(x2 * self._frame_width)),
            int(round(y2 * self._frame_height)),
        )

    # --- Frame handling ---
    def _on_slider(self, value: int) -> None:
        self.lbl_frame.setText(f"Frame {value} ({self._fmt_time(value)})")
        self.spin_frame.blockSignals(True)
        self.spin_frame.setValue(value)
        self.spin_frame.blockSignals(False)
        self._test_overlay_frame = None
        self._update_frame(value)

    def _on_goto_frame(self) -> None:
        """Apply the time-slice picker (frame index or mm:ss timestamp) to the slider."""
        target: int | None = None
        time_text = self.edt_time.text().strip()
        if time_text:
            try:
                seconds = self._parse_time(time_text)
            except ValueError as exc:
                QMessageBox.warning(self, "Time không hợp lệ", str(exc))
                return
            if self._fps <= 0:
                QMessageBox.warning(self, "Không có fps", "Video không khai báo fps; dùng frame index.")
                return
            target = int(round(seconds * self._fps))
        else:
            target = int(self.spin_frame.value())
        target = max(0, min(target, self._frame_total))
        self.slider.setValue(target)

    def _update_frame(self, index: int) -> None:
        if not self._source_id:
            return
        try:
            if self._test_overlay_frame is not None:
                self.canvas.set_frame(bgr_to_qpixmap(self._test_overlay_frame))
                return
            source = self._container.source_repo.get(self._source_id)
            frame = self._container.video_reader.get_frame(source.path, index)
            self.canvas.set_frame(bgr_to_qpixmap(frame))
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi đọc frame", str(exc))

    @staticmethod
    def _parse_time(text: str) -> float:
        """Accept ``mm:ss(.ms)``, ``hh:mm:ss(.ms)``, or plain seconds (int/float)."""
        text = text.strip()
        if not text:
            raise ValueError("empty time")
        if ":" not in text:
            try:
                return float(text)
            except ValueError as e:
                raise ValueError(f"không phải số giây hợp lệ: {text!r}") from e
        parts = text.split(":")
        if len(parts) == 2:
            mm, ss = parts
            return int(mm) * 60 + float(ss)
        if len(parts) == 3:
            hh, mm, ss = parts
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
        raise ValueError(f"định dạng time không hợp lệ: {text!r}")

    def _fmt_time(self, frame_idx: int) -> str:
        if self._fps <= 0:
            return "?"
        seconds = frame_idx / self._fps
        m = int(seconds // 60)
        s = seconds - m * 60
        return f"{m:02d}:{s:05.2f}"

    # --- Frame test / Save (Luồng 1b) ---
    def _on_test_detection(self) -> None:
        if not self._source_id:
            return
        idx = int(self.slider.value())
        try:
            svc = self._container.frame_extraction_service()
            result = svc.run_test_detection(
                self._source_id, idx, detection_roi=self._detection_roi_normalized()
            )
        except Exception as exc:
            QMessageBox.critical(self, "Test detection thất bại", str(exc))
            return

        self._test_overlay_frame = result.annotated_frame
        self.canvas.set_frame(bgr_to_qpixmap(result.annotated_frame))
        if result.counts_by_class:
            summary = ", ".join(f"{k}:{v}" for k, v in sorted(result.counts_by_class.items()))
        else:
            summary = "không phát hiện phương tiện"
        total = len(result.detections)
        self._last_test_summary = f"{total} detections — {summary}"
        self.lbl_detection_summary.setText(self._last_test_summary)
        self.lbl_detection_summary.setStyleSheet("color: #1a4f9c;")

    def _on_save_frame(self) -> None:
        if not self._source_id:
            return
        idx = int(self.slider.value())
        try:
            svc = self._container.frame_extraction_service()
            # If we just ran test detection, save the annotated frame; otherwise save raw frame.
            if self._test_overlay_frame is not None:
                path = svc.save_frame(self._test_overlay_frame, self._source_id, idx)
            else:
                source = self._container.source_repo.get(self._source_id)
                frame = self._container.video_reader.get_frame(source.path, idx)
                path = svc.save_frame(frame, self._source_id, idx)
        except Exception as exc:
            QMessageBox.critical(self, "Lưu frame thất bại", str(exc))
            return
        QMessageBox.information(self, "Đã lưu frame", str(path))

    # --- Tool & drawing ---
    def _set_tool(self, tool: Tool) -> None:
        self._tool = tool
        self.btn_polygon.setChecked(tool == Tool.POLYGON)
        self.btn_line.setChecked(tool == Tool.LINE)
        self.btn_detection_roi.setChecked(tool == Tool.DETECTION_ROI)

    def _cancel_draft(self) -> None:
        self._draft_poly = _DraftPolygon()
        self._draft_line = _DraftLine()
        self._draft_det_roi = _DraftDetectionROI()
        self.canvas.set_overlay_paint(self._paint_overlay)

    def _on_canvas_click(self, x: int, y: int) -> None:
        if self._tool == Tool.POLYGON:
            self._draft_poly.points.append((x, y))
        elif self._tool == Tool.LINE:
            if self._draft_line.start is None:
                self._draft_line.start = (x, y)
            else:
                self._draft_line.end = (x, y)
                self._commit_line()
        elif self._tool == Tool.DETECTION_ROI:
            if self._draft_det_roi.start is None:
                self._draft_det_roi.start = (x, y)
            else:
                self._commit_detection_roi(self._draft_det_roi.start, (x, y))
                self._draft_det_roi = _DraftDetectionROI()
                self._set_tool(Tool.NONE)
        self.canvas.set_overlay_paint(self._paint_overlay)

    def _on_canvas_double_click(self, x: int, y: int) -> None:
        if self._tool == Tool.POLYGON and len(self._draft_poly.points) >= 3:
            self._commit_polygon()
            self.canvas.set_overlay_paint(self._paint_overlay)

    def _commit_polygon(self) -> None:
        try:
            poly = ROIPolygon.from_points(
                f"zone_{len(self._polygons) + 1}", self._draft_poly.points
            )
        except Exception as exc:
            QMessageBox.warning(self, "Polygon không hợp lệ", str(exc))
            return
        self._polygons.append(poly)
        self._draft_poly = _DraftPolygon()
        self._refresh_lists()

    def _commit_detection_roi(
        self, p1: tuple[int, int], p2: tuple[int, int]
    ) -> None:
        x1, x2 = sorted((p1[0], p2[0]))
        y1, y2 = sorted((p1[1], p2[1]))
        if x2 - x1 < 2 or y2 - y1 < 2:
            QMessageBox.warning(
                self,
                "Detection ROI quá nhỏ",
                "Vùng được vẽ gần như là 1 điểm — chọn 2 góc cách nhau ít nhất 2 pixel.",
            )
            return
        self._detection_roi_px = (x1, y1, x2, y2)
        self._refresh_detection_roi_label()

    def _clear_detection_roi(self) -> None:
        self._detection_roi_px = None
        self._draft_det_roi = _DraftDetectionROI()
        self._refresh_detection_roi_label()
        if self._tool == Tool.DETECTION_ROI:
            self._set_tool(Tool.NONE)
        self.canvas.set_overlay_paint(self._paint_overlay)

    def _refresh_detection_roi_label(self) -> None:
        bounds = self._detection_roi_normalized()
        if bounds is None:
            self.lbl_detection_roi.setText("Chưa cấu hình → dùng default từ inference.yaml")
            self.lbl_detection_roi.setStyleSheet("color: #555;")
        else:
            x1, y1, x2, y2 = bounds
            self.lbl_detection_roi.setText(
                f"Bounds (chuẩn hoá): [{x1:.3f}, {y1:.3f}, {x2:.3f}, {y2:.3f}]"
            )
            self.lbl_detection_roi.setStyleSheet("color: #1a4f9c;")

    def _detection_roi_normalized(
        self,
    ) -> tuple[float, float, float, float] | None:
        if self._detection_roi_px is None or self._frame_width <= 0 or self._frame_height <= 0:
            return None
        x1, y1, x2, y2 = self._detection_roi_px
        return (
            x1 / self._frame_width,
            y1 / self._frame_height,
            x2 / self._frame_width,
            y2 / self._frame_height,
        )

    def _commit_line(self) -> None:
        try:
            line = CountingLine(
                f"line_{len(self._lines) + 1}",
                start=self._draft_line.start,
                end=self._draft_line.end,
                direction=LineDirection(self.cmb_direction.currentText()),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Line không hợp lệ", str(exc))
            self._draft_line = _DraftLine()
            return
        self._lines.append(line)
        self._draft_line = _DraftLine()
        self._refresh_lists()

    def _remove_selected(self) -> None:
        if self.list_polygons.currentRow() >= 0:
            self._polygons.pop(self.list_polygons.currentRow())
        elif self.list_lines.currentRow() >= 0:
            self._lines.pop(self.list_lines.currentRow())
        self._refresh_lists()

    def _refresh_lists(self) -> None:
        self.list_polygons.clear()
        for p in self._polygons:
            self.list_polygons.addItem(QListWidgetItem(f"{p.name} ({len(p.points)} điểm)"))
        self.list_lines.clear()
        for l in self._lines:
            self.list_lines.addItem(
                QListWidgetItem(f"{l.name} {l.start}->{l.end} [{l.direction.value}]")
            )
        self.canvas.set_overlay_paint(self._paint_overlay)

    # --- Painting ---
    def _paint_overlay(self, painter: QPainter, rect, scale) -> None:
        sx, sy = scale

        def to_pt(p: tuple[int, int]) -> QPointF:
            return QPointF(p[0] * sx, p[1] * sy)

        # Existing polygons
        painter.setPen(QPen(QColor(0, 200, 0), 2))
        painter.setBrush(QColor(0, 200, 0, 60))
        for poly in self._polygons:
            qpoly = QPolygon([to_pt(p).toPoint() for p in poly.points])
            painter.drawPolygon(qpoly)

        # Draft polygon
        painter.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if len(self._draft_poly.points) >= 2:
            for i in range(len(self._draft_poly.points) - 1):
                painter.drawLine(to_pt(self._draft_poly.points[i]), to_pt(self._draft_poly.points[i + 1]))
        for pt in self._draft_poly.points:
            painter.drawEllipse(to_pt(pt), 4, 4)

        # Existing lines
        painter.setPen(QPen(QColor(255, 50, 50), 3))
        for line in self._lines:
            painter.drawLine(to_pt(line.start), to_pt(line.end))

        # Draft line
        painter.setPen(QPen(QColor(255, 200, 0), 3, Qt.PenStyle.DashLine))
        if self._draft_line.start is not None:
            painter.drawEllipse(to_pt(self._draft_line.start), 4, 4)

        # Detection ROI (vùng cần detect — blue dashed rectangle)
        if self._detection_roi_px is not None:
            painter.setPen(QPen(QColor(0, 150, 255), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            x1, y1, x2, y2 = self._detection_roi_px
            top_left = to_pt((x1, y1))
            bot_right = to_pt((x2, y2))
            painter.drawRect(
                int(top_left.x()),
                int(top_left.y()),
                int(bot_right.x() - top_left.x()),
                int(bot_right.y() - top_left.y()),
            )
            painter.drawText(int(top_left.x()) + 4, int(top_left.y()) + 16, "Detection ROI")

        # Draft Detection ROI first-corner marker
        if self._draft_det_roi.start is not None:
            painter.setPen(QPen(QColor(0, 150, 255), 2, Qt.PenStyle.DashLine))
            painter.drawEllipse(to_pt(self._draft_det_roi.start), 5, 5)

    # --- Persistence ---
    def _save_config(self) -> None:
        if not self._source_id:
            return
        cfg = ROIConfig(
            source_id=self._source_id,
            reference_frame_index=self.slider.value(),
            roi_polygons=list(self._polygons),
            counting_lines=list(self._lines),
            pixels_per_meter=float(self.spin_ppm.value()),
            detection_roi=self._detection_roi_normalized(),
        )
        try:
            self._container.roi_config_service().save_config(cfg)
            QMessageBox.information(self, "Đã lưu", "ROI config đã lưu.")
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi", str(exc))

    def _load_config(self) -> None:
        if not self._source_id:
            return
        try:
            cfg = self._container.roi_config_service().load_config(self._source_id)
        except Exception as exc:
            QMessageBox.warning(self, "Không có config", str(exc))
            return
        self._polygons = list(cfg.roi_polygons)
        self._lines = list(cfg.counting_lines)
        self.spin_ppm.setValue(cfg.pixels_per_meter)
        self.slider.setValue(cfg.reference_frame_index)
        self._detection_roi_px = self._normalized_to_pixels(cfg.detection_roi)
        self._refresh_detection_roi_label()
        self._refresh_lists()
