"""GUI entry point — invoked by ``python -m src.adapters.input.gui.app``."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from src.adapters.input.gui.main_window import MainWindow
from src.bootstrap.container import Container
from src.bootstrap.inference_config import InferenceConfig
from src.bootstrap.paths import DEFAULT_DATA_DIR
from src.domain.value_objects import apply_pce_overrides


def main() -> int:
    config = InferenceConfig.load()
    apply_pce_overrides(config.vehicle_pce.as_mapping())

    container = Container(data_dir=DEFAULT_DATA_DIR, inference_config=config)
    app = QApplication(sys.argv)
    win = MainWindow(container)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
