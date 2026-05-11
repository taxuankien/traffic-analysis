"""Helpers for converting OpenCV BGR frames to QImage/QPixmap."""
from __future__ import annotations

import numpy as np
from PyQt6.QtGui import QImage, QPixmap


def bgr_to_qpixmap(frame: np.ndarray) -> QPixmap:
    if frame is None:
        return QPixmap()
    rgb = frame[..., ::-1].copy()  # BGR -> RGB
    h, w = rgb.shape[:2]
    bytes_per_line = 3 * w
    img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img.copy())  # copy detaches from numpy buffer
