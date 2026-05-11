"""Sanity-check the GUI time-string parser without spinning up Qt."""
from __future__ import annotations

import pytest

from src.adapters.input.gui.roi_editor import ROIEditorWidget


def test_plain_seconds():
    assert ROIEditorWidget._parse_time("83.5") == 83.5
    assert ROIEditorWidget._parse_time("0") == 0.0


def test_mm_ss():
    assert ROIEditorWidget._parse_time("1:23.5") == 83.5
    assert ROIEditorWidget._parse_time("0:00") == 0.0
    assert ROIEditorWidget._parse_time("10:00") == 600.0


def test_hh_mm_ss():
    assert ROIEditorWidget._parse_time("1:00:30") == 3630.0


def test_invalid():
    with pytest.raises(ValueError):
        ROIEditorWidget._parse_time("abc")
    with pytest.raises(ValueError):
        ROIEditorWidget._parse_time("")
    with pytest.raises(ValueError):
        ROIEditorWidget._parse_time("1:2:3:4")
