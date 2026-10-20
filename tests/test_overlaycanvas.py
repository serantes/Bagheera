"""
Tests for the OverlayCanvas widget.

Covers the comparison modes (toggle, difference, opacity), layer swapping,
view reset and the fit/1:1 toggle behaviour.
"""
import pytest
from PySide6.QtGui import QImage, QPixmap

from bagheeraview.core.overlaycanvas import OverlayCanvas


@pytest.fixture(autouse=True)
def _qapp():
    """Ensures a QApplication exists for every test in this module."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def canvas():
    """Builds a canvas pre-loaded with two solid-color layers."""
    c = OverlayCanvas()
    c.resize(200, 200)

    red = QImage(100, 100, QImage.Format_RGB32)
    red.fill("#ff0000")
    blue = QImage(100, 100, QImage.Format_RGB32)
    blue.fill("#0000ff")

    c.set_pixmaps(QPixmap.fromImage(blue), QPixmap.fromImage(red))
    return c


def test_swap_layers_swaps_pixmaps(canvas):
    """Swap Layers must exchange the top and bottom pixmaps."""
    top_before = canvas._top
    bottom_before = canvas._bottom
    canvas.swap_layers()
    assert canvas._top is bottom_before
    assert canvas._bottom is top_before


def test_reset_view_clears_top_transform(canvas):
    """Reset View restores the default top layer transform."""
    canvas.zoom_top(2.0)
    canvas._top_offset = canvas._top_offset + type(canvas._top_offset)(30, 30)
    canvas.reset_view()
    assert canvas._top_zoom_mul == 1.0
    assert canvas._top_offset.isNull()


def test_set_opacity_clamps_value(canvas):
    """Opacity values outside 0-100 must be clamped."""
    canvas.set_opacity(150)
    assert canvas._opacity == 1.0
    canvas.set_opacity(-20)
    assert canvas._opacity == 0.0
    canvas.set_opacity(40)
    assert canvas._opacity == 0.4


def test_toggle_fit_actual_switches_zoom(canvas):
    """Fit/1:1 toggling alternates between the fit zoom and 1.0."""
    initial = canvas._view_zoom
    assert abs(initial - 2.0) < 1e-6  # 100x100 image fit into 200x200 widget
    canvas.toggle_fit_actual()
    assert abs(canvas._view_zoom - 1.0) < 1e-6
    canvas.toggle_fit_actual()
    assert abs(canvas._view_zoom - initial) < 1e-6


def test_difference_mode_identical_images_is_black(canvas):
    """Pixel difference of identical layers yields all-black pixels."""
    top = QPixmap(canvas._top)
    canvas.set_pixmaps(top, QPixmap(top))  # identical layers
    canvas.set_mode(OverlayCanvas.MODE_DIFFERENCE)
    rendered = canvas.grab()
    # Center of the image area must be pure black in difference mode.
    color = rendered.toImage().pixelColor(100, 100)
    assert color.red() == 0 and color.green() == 0 and color.blue() == 0
