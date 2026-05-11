from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QStackedWidget

from src.adapters.input.gui.analysis_dashboard import AnalysisDashboardWidget
from src.adapters.input.gui.results_viewer import ResultsViewerWidget
from src.adapters.input.gui.roi_editor import ROIEditorWidget
from src.adapters.input.gui.source_manager import SourceManagerWidget
from src.bootstrap.container import Container


class MainWindow(QMainWindow):
    def __init__(self, container: Container) -> None:
        super().__init__()
        self.setWindowTitle("Traffic Analysis")
        self.resize(1280, 800)
        self._container = container

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self.source_mgr = SourceManagerWidget(container)
        self.roi_editor = ROIEditorWidget(container)
        self.dashboard = AnalysisDashboardWidget(container)
        self.results = ResultsViewerWidget(container)

        for w in (self.source_mgr, self.roi_editor, self.dashboard, self.results):
            self._stack.addWidget(w)

        self.source_mgr.open_roi_editor.connect(self._open_roi)
        self.source_mgr.run_analysis.connect(self._open_analysis)
        self.source_mgr.view_results.connect(self._open_results)

        self.roi_editor.back_requested.connect(self._show_sources)
        self.dashboard.back_requested.connect(self._show_sources)
        self.dashboard.finished.connect(self._on_dashboard_finished)
        self.results.back_requested.connect(self._show_sources)

        self._show_sources()

    def _show_sources(self) -> None:
        self.source_mgr.refresh()
        self._stack.setCurrentWidget(self.source_mgr)

    def _open_roi(self, source_id: str) -> None:
        self.roi_editor.load_source(source_id)
        self._stack.setCurrentWidget(self.roi_editor)

    def _open_analysis(self, source_id: str) -> None:
        self.dashboard.set_source(source_id)
        self._stack.setCurrentWidget(self.dashboard)

    def _open_results(self, source_id: str) -> None:
        self.results.set_source(source_id)
        self._stack.setCurrentWidget(self.results)

    def _on_dashboard_finished(self, source_id: str, session_id: str) -> None:
        # Stay on the dashboard so the user can review the populated table.
        pass
