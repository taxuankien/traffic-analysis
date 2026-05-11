from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.bootstrap.container import Container


class SourceManagerWidget(QWidget):
    open_roi_editor = pyqtSignal(str)
    run_analysis = pyqtSignal(str)
    view_results = pyqtSignal(str)

    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Tên", "Đường dẫn", "Tạo lúc"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Thêm video")
        self.btn_remove = QPushButton("Xoá")
        self.btn_roi = QPushButton("Cấu hình ROI")
        self.btn_run = QPushButton("Phân tích")
        self.btn_results = QPushButton("Xem kết quả")
        for b in (self.btn_add, self.btn_remove, self.btn_roi, self.btn_run, self.btn_results):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_roi.clicked.connect(lambda: self._emit_with_selected(self.open_roi_editor))
        self.btn_run.clicked.connect(lambda: self._emit_with_selected(self.run_analysis))
        self.btn_results.clicked.connect(lambda: self._emit_with_selected(self.view_results))

    def refresh(self) -> None:
        sources = self._container.data_management_service().list_sources()
        self.table.setRowCount(len(sources))
        for i, s in enumerate(sources):
            self.table.setItem(i, 0, QTableWidgetItem(s.id))
            self.table.setItem(i, 1, QTableWidgetItem(s.name))
            self.table.setItem(i, 2, QTableWidgetItem(s.path))
            self.table.setItem(i, 3, QTableWidgetItem(s.created_at.isoformat(timespec="seconds")))

    def _selected_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _emit_with_selected(self, signal: pyqtSignal) -> None:
        sid = self._selected_id()
        if sid is None:
            QMessageBox.information(self, "Thiếu lựa chọn", "Hãy chọn một nguồn video trước.")
            return
        signal.emit(sid)

    def _on_add(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn video", filter="Video (*.mp4 *.avi *.mov *.mkv)"
        )
        if not path:
            return
        name, ok = QInputDialog.getText(self, "Tên nguồn", "Đặt tên cho nguồn video:")
        if not ok or not name.strip():
            return
        try:
            self._container.data_management_service().add_source(name.strip(), path)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi", f"Không thể thêm nguồn: {exc}")

    def _on_remove(self) -> None:
        sid = self._selected_id()
        if sid is None:
            return
        if (
            QMessageBox.question(self, "Xác nhận", f"Xoá nguồn {sid}?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self._container.data_management_service().delete_source(sid)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi", str(exc))
