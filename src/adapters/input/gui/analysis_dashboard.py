from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.application.ports.input.analysis_port import AnalysisProgress
from src.bootstrap.container import Container


class _AnalysisWorker(QObject):
    progress = pyqtSignal(int, int, int)  # current, total, intervals
    finished_ok = pyqtSignal(str, str)  # session_id, annotated_path (empty when disabled)
    failed = pyqtSignal(str)

    def __init__(
        self,
        container: Container,
        source_id: str,
        interval_seconds: float,
        annotated_output_path: str | None,
    ) -> None:
        super().__init__()
        self._container = container
        self._source_id = source_id
        self._interval_seconds = interval_seconds
        self._annotated_output_path = annotated_output_path

    def run(self) -> None:
        try:
            meta = self._container.video_reader.get_metadata(
                self._container.source_repo.get(self._source_id).path
            )
            service = self._container.analysis_service(frame_rate=int(meta.fps) or 30)
            session = service.start_session(self._source_id, interval_seconds=self._interval_seconds)

            def cb(p: AnalysisProgress) -> None:
                self.progress.emit(p.current_frame, p.total_frames, p.intervals_completed)

            # Resolve the annotated path now that we know the session id.
            output_path: str | None = None
            if self._annotated_output_path:
                tpl = self._annotated_output_path
                output_path = tpl.format(session_id=session.id, source_id=self._source_id)
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            service.run_session(
                session.id,
                progress_cb=cb,
                annotated_output_path=output_path,
            )
            self.finished_ok.emit(session.id, output_path or "")
        except Exception as exc:
            self.failed.emit(str(exc))


class AnalysisDashboardWidget(QWidget):
    back_requested = pyqtSignal()
    finished = pyqtSignal(str, str)  # source_id, session_id

    # Device combobox encodes the override value in user-data:
    #   None  → tôn trọng cấu hình YAML (model.device)
    #   "cpu" → chạy bằng CPU
    #   "cuda:N" → chạy bằng GPU NVIDIA index N
    _DEVICE_AUTO_LABEL = "Tự động (theo cấu hình)"
    _DEVICE_CPU_LABEL = "CPU"

    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._source_id: str | None = None
        self._thread: QThread | None = None
        self._worker: _AnalysisWorker | None = None
        self._monitor = container.system_monitor()
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(1000)
        self._monitor_timer.timeout.connect(self._refresh_monitor)
        self._build()
        self._refresh_monitor()
        self._monitor_timer.start()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        self.lbl_source = QLabel("Nguồn: (chưa chọn)")
        root.addWidget(self.lbl_source)

        form = QFormLayout()
        self.spin_interval = QDoubleSpinBox()
        self.spin_interval.setMinimum(1.0)
        self.spin_interval.setMaximum(600.0)
        self.spin_interval.setValue(30.0)
        form.addRow("Interval (giây):", self.spin_interval)

        self.cmb_device = QComboBox()
        self._populate_device_combo()
        form.addRow("Thiết bị inference:", self.cmb_device)

        self.chk_annotate = QCheckBox("Lưu video gán nhãn vào data/results/<source>/<session>_annotated.mp4")
        self.chk_annotate.setChecked(True)
        form.addRow("Output video:", self.chk_annotate)
        root.addLayout(form)

        root.addWidget(self._build_monitor_panel())

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("Bắt đầu phân tích")
        self.btn_back = QPushButton("Quay lại")
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_back)
        root.addLayout(btn_row)

        self.progress = QProgressBar()
        root.addWidget(self.progress)
        self.lbl_status = QLabel("")
        root.addWidget(self.lbl_status)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Timestamp",
                "Car (in/out)",
                "Motorcycle (in/out)",
                "Bus (in/out)",
                "Truck (in/out)",
                "Total",
                "Flow (PCU/h)",
                "Queue",
                "Occupancy",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self.btn_start.clicked.connect(self._start)
        self.btn_back.clicked.connect(self.back_requested.emit)

    def _populate_device_combo(self) -> None:
        self.cmb_device.clear()
        self.cmb_device.addItem(self._DEVICE_AUTO_LABEL, None)
        self.cmb_device.addItem(self._DEVICE_CPU_LABEL, "cpu")
        cuda_devices = [d for d in self._monitor.available_devices() if d.startswith("cuda")]
        if not cuda_devices:
            # No CUDA — keep an explanatory disabled entry so users can see *why*.
            self.cmb_device.addItem("GPU (không phát hiện CUDA)", None)
            idx = self.cmb_device.count() - 1
            self.cmb_device.model().item(idx).setEnabled(False)
            return
        names_by_device = {f"cuda:{g.index}": g.name for g in self._monitor.snapshot().gpus}
        for d in cuda_devices:
            name = names_by_device.get(d)
            label = f"GPU {d} — {name}" if name else f"GPU {d}"
            self.cmb_device.addItem(label, d)

    def _build_monitor_panel(self) -> QWidget:
        box = QGroupBox("Tài nguyên hệ thống")
        layout = QFormLayout(box)
        self.lbl_cpu = QLabel("—")
        self.lbl_ram = QLabel("—")
        self.lbl_gpu = QLabel("—")
        layout.addRow("CPU:", self.lbl_cpu)
        layout.addRow("RAM:", self.lbl_ram)
        layout.addRow("GPU:", self.lbl_gpu)
        return box

    def _refresh_monitor(self) -> None:
        snap = self._monitor.snapshot()
        self.lbl_cpu.setText(f"{snap.cpu_percent:5.1f}%")
        if snap.ram_total_mb > 0:
            self.lbl_ram.setText(
                f"{snap.ram_percent:5.1f}%  ({snap.ram_used_mb:,.0f} / {snap.ram_total_mb:,.0f} MB)"
            )
        else:
            self.lbl_ram.setText("không khả dụng (cần psutil)")
        if not snap.gpus:
            self.lbl_gpu.setText("không có GPU CUDA")
            return
        lines = []
        for g in snap.gpus:
            util = f"{g.utilization_percent:5.1f}%" if g.utilization_percent is not None else "N/A"
            lines.append(
                f"[{g.index}] {g.name} — util {util}, "
                f"VRAM {g.memory_used_mb:,.0f} / {g.memory_total_mb:,.0f} MB ({g.memory_percent:.1f}%)"
            )
        self.lbl_gpu.setText("\n".join(lines))

    def set_source(self, source_id: str) -> None:
        self._source_id = source_id
        try:
            src = self._container.source_repo.get(source_id)
            self.lbl_source.setText(f"Nguồn: {src.name} — {src.path}")
        except Exception as exc:
            self.lbl_source.setText(f"(lỗi nạp nguồn) {exc}")

    def _start(self) -> None:
        if not self._source_id:
            QMessageBox.warning(self, "Thiếu nguồn", "Chưa chọn nguồn.")
            return
        if self._thread is not None and self._thread.isRunning():
            return

        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.lbl_status.setText("Đang khởi động...")
        self.btn_start.setEnabled(False)

        device = self.cmb_device.currentData()
        self._container.set_device_override(device)

        annotated_template: str | None = None
        if self.chk_annotate.isChecked():
            results_root = Path(self._container.data_dir) / "results" / self._source_id
            annotated_template = str(results_root / "{session_id}_annotated.mp4")

        self._thread = QThread(self)
        self._worker = _AnalysisWorker(
            self._container,
            self._source_id,
            float(self.spin_interval.value()),
            annotated_template,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_progress(self, current: int, total: int, intervals: int) -> None:
        if total > 0:
            self.progress.setValue(min(100, int(current * 100 / total)))
        self.lbl_status.setText(f"Frame {current}/{total} — đã có {intervals} interval")

    def _on_finished(self, session_id: str, annotated_path: str) -> None:
        msg = f"Hoàn thành. Session: {session_id}"
        if annotated_path:
            msg += f"\nVideo gán nhãn: {annotated_path}"
        self.lbl_status.setText(msg)
        self.btn_start.setEnabled(True)
        self.progress.setValue(100)
        self._populate_table(session_id)
        if self._source_id:
            self.finished.emit(self._source_id, session_id)

    def _on_failed(self, message: str) -> None:
        self.lbl_status.setText(f"Lỗi: {message}")
        self.btn_start.setEnabled(True)
        QMessageBox.critical(self, "Phân tích thất bại", message)

    def _cleanup_thread(self) -> None:
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _populate_table(self, session_id: str) -> None:
        if not self._source_id:
            return
        intervals = self._container.interval_repo.list(self._source_id, session_id)
        self.table.setRowCount(len(intervals))
        for r, itv in enumerate(intervals):
            self.table.setItem(r, 0, QTableWidgetItem(itv.timestamp.isoformat(timespec="seconds")))
            for col, name in enumerate(("car", "motorcycle", "bus", "truck"), start=1):
                in_v = itv.counts_in.get(name, 0)
                out_v = itv.counts_out.get(name, 0)
                self.table.setItem(r, col, QTableWidgetItem(f"{in_v}/{out_v}"))
            self.table.setItem(r, 5, QTableWidgetItem(str(itv.total_count())))
            self.table.setItem(r, 6, QTableWidgetItem(f"{itv.flow_rate_pcu:.0f}"))
            self.table.setItem(r, 7, QTableWidgetItem(str(itv.queue_length)))
            self.table.setItem(r, 8, QTableWidgetItem(f"{itv.occupancy_ratio:.2%}"))
