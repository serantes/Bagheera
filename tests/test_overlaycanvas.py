"""
Tests for the OverlayCanvas widget.

Covers the comparison modes (toggle, difference, opacity), layer swapping,
independent per-layer transforms, view reset, zoom beyond the widget size and
the fit/1:1 toggle behaviour.
"""
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPixmap

from bagheeraview.core.overlaycanvas import (
    OverlayCanvas, LAYER_TOP, LAYER_BOTTOM, LAYER_BOTH
)


@pytest.fixture(autouse=True)
def _qapp():
    """Ensures a QApplication exists for every test in this module."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _solid(color, w=100, h=100):
    """Returns a solid-color QPixmap of the given size."""
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


@pytest.fixture()
def canvas():
    """Builds a canvas pre-loaded with two solid-color layers."""
    c = OverlayCanvas()
    c.resize(200, 200)
    c.set_pixmaps(_solid("#0000ff"), _solid("#ff0000"))
    return c


def test_swap_layers_swaps_pixmaps_and_keeps_states(canvas):
    """Swap Layers exchanges pixmaps and their per-layer transforms."""
    top_before = canvas._top
    bottom_before = canvas._bottom
    canvas._top_state.zoom = 2.5
    canvas._top_state.offset = QPointF(7.0, -3.0)
    bottom_state = canvas._bottom_state
    canvas.swap_layers()
    assert canvas._top is bottom_before
    assert canvas._bottom is top_before
    # The zoomed state travels with its image (now on the bottom).
    assert canvas._bottom_state.zoom == 2.5
    assert canvas._bottom_state.offset == QPointF(7.0, -3.0)
    assert canvas._top_state is bottom_state
    assert canvas._swapped


def test_reset_view_clears_transforms(canvas):
    """Reset View restores the default fit state of both layers."""
    canvas.zoom_layers(2.0, LAYER_TOP, None)
    canvas._top_state.offset = QPointF(30, 30)
    canvas.reset_view()
    assert canvas._top_state.zoom == 1.0
    assert canvas._bottom_state.zoom == 1.0
    assert canvas._top_state.offset.isNull()


def test_set_opacity_clamps_value(canvas):
    """Opacity values outside 0-100 must be clamped."""
    canvas.set_opacity(150)
    assert canvas._opacity == 1.0
    canvas.set_opacity(-20)
    assert canvas._opacity == 0.0
    canvas.set_opacity(40)
    assert canvas._opacity == 0.4


def test_toggle_fit_actual_switches_zoom(canvas):
    """Fit/1:1 toggling alternates between the fit state and real pixels."""
    assert canvas._bottom_state.zoom == 1.0  # 100x100 fits as 2x on 200x200
    canvas.toggle_fit_actual()
    assert abs(canvas._fit_scale(canvas._bottom) *
               canvas._bottom_state.zoom - 1.0) < 1e-6
    canvas.toggle_fit_actual()
    assert canvas._bottom_state.zoom == 1.0


def test_zoom_layers_targets_are_independent(canvas):
    """Shift/Ctrl targeting must only modify the affected layer."""
    canvas.zoom_layers(2.0, LAYER_TOP, None)
    assert canvas._top_state.zoom == 2.0
    assert canvas._bottom_state.zoom == 1.0
    canvas.zoom_layers(0.5, LAYER_BOTTOM, None)
    assert canvas._top_state.zoom == 2.0
    assert canvas._bottom_state.zoom == 0.5
    canvas.zoom_layers(3.0, LAYER_BOTH, None)
    assert abs(canvas._top_state.zoom - 6.0) < 1e-9
    assert abs(canvas._bottom_state.zoom - 1.5) < 1e-9


def test_zoom_preserves_pixel_under_anchor(canvas):
    """The source pixel under the zoom anchor stays fixed."""
    anchor = QPointF(150, 120)
    # Offset the layer so at the anchor we are looking at the image center:
    # dest_center (100,100) plus offset places the image at the anchor.
    canvas._bottom_state.offset = QPointF(50.0, 20.0)
    before = (canvas._bottom.width() / 2.0, canvas._bottom.height() / 2.0)
    canvas.zoom_layers(2.0, LAYER_BOTTOM, anchor)
    # Reconstruct the source pixel visible at the anchor after the zoom.
    fit = canvas._fit_scale(canvas._bottom)
    state = canvas._bottom_state
    scale = fit * state.zoom
    dest_w = canvas._bottom.width() * scale
    dest_h = canvas._bottom.height() * scale
    dest_x = canvas.width() / 2.0 + state.offset.x() - dest_w / 2.0
    dest_y = canvas.height() / 2.0 + state.offset.y() - dest_h / 2.0
    sx = canvas._bottom.width() / dest_w
    sy = canvas._bottom.height() / dest_h
    src_after = ((anchor.x() - dest_x) * sx, (anchor.y() - dest_y) * sy)
    assert abs(src_after[0] - before[0]) < 1e-6
    assert abs(src_after[1] - before[1]) < 1e-6


def test_difference_mode_identical_images_is_black(canvas):
    """Pixel difference of identical layers yields all-black pixels."""
    top = QPixmap(canvas._top)
    canvas.set_pixmaps(top, QPixmap(top))  # identical layers
    canvas.set_mode(OverlayCanvas.MODE_DIFFERENCE)
    rendered = canvas.grab()
    color = rendered.toImage().pixelColor(100, 100)
    assert color.red() == 0 and color.green() == 0 and color.blue() == 0


def test_zoom_beyond_widget_shows_expected_source_area():
    """The zoom can exceed the widget and the source mapping stays exact."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication

    c = OverlayCanvas()
    c.resize(400, 300)

    # 200x100 black image with a white 50x50 center marker.
    img = QImage(200, 100, QImage.Format_RGB32)
    img.fill(QColor("#000000"))
    for y in range(25, 75):
        for x in range(75, 125):
            img.setPixelColor(x, y, QColor("#ffffff"))
    pixmap = QPixmap.fromImage(img)
    c.set_pixmaps(pixmap, QPixmap(pixmap))
    # Absolute scale 4x: fit is 2.0 (min(400/200, 300/100)), so zoom=2.
    c.zoom_layers(2.0, LAYER_BOTH, None)
    c.show()
    QApplication.processEvents()
    rendered = c.grab()
    out = rendered.toImage()
    # The visible source rect maps 1:1 to the widget (400x300 at scale 4x
    # shows a 100x75 source window centered on the marker center).
    assert out.pixelColor(94, 100).name() == "#000000"  # left of marker edge
    assert out.pixelColor(200, 150).name() == "#ffffff"  # exact image center
    assert out.pixelColor(380, 150).name() == "#000000"  # right of marker
