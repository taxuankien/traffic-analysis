from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.bootstrap.container import Container


class ResultsViewerWidget(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._source_id: str | None = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Session:"))
        self.cmb_session = QComboBox()
        filter_row.addWidget(self.cmb_session, 1)

        filter_row.addWidget(QLabel("Từ:"))
        self.dt_start = QDateTimeEdit()
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setDateTime(datetime(2000, 1, 1, 0, 0, 0))
        filter_row.addWidget(self.dt_start)

        filter_row.addWidget(QLabel("Đến:"))
        self.dt_end = QDateTimeEdit()
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setDateTime(datetime(2099, 1, 1, 0, 0, 0))
        filter_row.addWidget(self.dt_end)

        self.btn_apply = QPushButton("Lọc")
        filter_row.addWidget(self.btn_apply)
        root.addLayout(filter_row)

        self.table = QTableWidget(0, 10)
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
                "Speed (km/h)",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        self.btn_export = QPushButton("Xuất CSV")
        self.btn_back = QPushButton("Quay lại")
        action_row.addStretch(1)
        action_row.addWidget(self.btn_export)
        action_row.addWidget(self.btn_back)
        root.addLayout(action_row)

        self.btn_apply.clicked.connect(self._refresh)
        self.btn_export.clicked.connect(self._export)
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.cmb_session.currentIndexChanged.connect(self._refresh)

    def set_source(self, source_id: str) -> None:
        self._source_id = source_id
        self._refresh_sessions()
        self._refresh()

    def _refresh_sessions(self) -> None:
        self.cmb_session.blockSignals(True)
        self.cmb_session.clear()
        self.cmb_session.addItem("(Tất cả)", userData=None)
        if self._source_id:
            sessions = self._container.session_repo.list_for_source(self._source_id)
            for s in sessions:
                self.cmb_session.addItem(f"{s.id} [{s.status.value}]", userData=s.id)
        self.cmb_session.blockSignals(False)

    def _selected_session(self) -> str | None:
        return self.cmb_session.currentData()

    def _refresh(self) -> None:
        self.table.setRowCount(0)
        if not self._source_id:
            return
        start = self.dt_start.dateTime().toPyDateTime()
        end = self.dt_end.dateTime().toPyDateTime()
        try:
            intervals = self._container.data_management_service().query_intervals(
                self._source_id,
                session_id=self._selected_session(),
                start=start,
                end=end,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi", str(exc))
            return

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
            self.table.setItem(r, 9, QTableWidgetItem(f"{itv.avg_speed_kmh:.1f}"))

    def _export(self) -> None:
        if not self._source_id:
            return
        sid = self._selected_session()
        if sid is None:
            QMessageBox.information(
                self, "Chọn session", "Hãy chọn một session cụ thể để xuất CSV."
            )
            return
        path, _ = QFileDialog.getSaveFileName(self, "Xuất CSV", filter="CSV (*.csv)")
        if not path:
            return
        try:
            out = self._container.data_management_service().export_csv(
                self._source_id, sid, path
            )
            QMessageBox.information(self, "Xuất thành công", f"Đã ghi: {out}")
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi", str(exc))
