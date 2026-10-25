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
    # grab() returns an image in device pixels (pixelRatio == 1 under the
    # offscreen platform but 2 on HiDPI Wayland/X11 sessions), while
    # pixelColor() samples in those device coordinates. Normalizing to the
    # widget's logical size keeps the assertions resolution-independent.
    if out.devicePixelRatio() != 1.0:
        out = out.scaled(c.width(), c.height())
    # The visible source rect maps 1:1 to the widget (400x300 at scale 4x
    # shows a 100x75 source window centered on the marker center). The marker
    # spans logical x=100..300 (white), with black on either side.
    assert out.pixelColor(50, 150).name() == "#000000"  # left of marker edge
    assert out.pixelColor(200, 150).name() == "#ffffff"  # exact image center
    assert out.pixelColor(350, 150).name() == "#000000"  # right of marker


def _quadrants(w=120, h=60):
    """
    Builds a rectangular image with a distinct color in each quadrant.

    The four colors make any 90-degree rotation or axis flip detectable.

    Args:
        w (int): Width of the image.
        h (int): Height of the image.

    Returns:
        QPixmap: The four-quadrant test image.
    """
    from PySide6.QtGui import QColor

    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("#000000"))
    for y in range(h):
        for x in range(w):
            left = x * 2 < w
            top = y * 2 < h
            color = {
                (True, True): "#ff0000",      # top-left red
                (False, True): "#00ff00",     # top-right green
                (True, False): "#0000ff",     # bottom-left blue
                (False, False): "#ffff00",    # bottom-right yellow
            }[(left, top)]
            img.setPixelColor(x, y, QColor(color))
    return QPixmap.fromImage(img)


def _expect_corners(c, top_left, top_right):
    """
    Asserts the dominant colors of the top row of the canvas top layer.

    The corner pixels of a 120x60 image sit exactly on the rotated quadrant
    seams, so a pure seam sample can mix colours (Qt's smooth rotation).
    Instead the dominant hue is computed over small patches that live fully
    inside the left and right quadrants.

    Args:
        c (OverlayCanvas): The canvas whose top layer is sampled.
        top_left (str): Expected dominant colour of the left half of the
            top row.
        top_right (str): Expected dominant colour of the right half.
    """
    img = c._top.toImage()
    height = img.height()
    left_col = int(img.width() * 0.25)
    right_col = int(img.width() * 0.75)
    for col in (left_col, right_col):
        counts = {}
        for dy in range(4):
            for dx in range(4):
                name = img.pixelColor(col + dx - 2,
                                      round(height * 0.25) + dy - 2).name()
                counts[name] = counts.get(name, 0) + 1
        dominant = max(counts, key=counts.get)
        expected = top_left if col == left_col else top_right
        assert dominant == expected, 'expected {} got {} at x={}'.format(
            expected, dominant, col)


def test_rotate_top_left_swaps_dimensions_and_pixels(canvas):
    """Rotate Left swaps a rectangular layer's dimensions and orientation."""
    c = OverlayCanvas()
    c.set_pixmaps(_quadrants(w=120, h=60), _solid("#ff0000"))
    before = (c._top.width(), c._top.height())
    c.rotate_top(clockwise=False)
    assert (c._top.width(), c._top.height()) == (before[1], before[0])
    c.rotate_top(clockwise=False)
    assert (c._top.width(), c._top.height()) == (before[0], before[1])
    c.rotate_top(clockwise=False)
    assert (c._top.width(), c._top.height()) == (before[1], before[0])
    c.rotate_top(clockwise=False)
    assert (c._top.width(), c._top.height()) == (before[0], before[1])


def test_rotate_top_right_swaps_dimensions_and_pixels(canvas):
    """Rotate Right swaps a rectangular layer's dimensions and orientation."""
    c = OverlayCanvas()
    c.set_pixmaps(_quadrants(w=120, h=60), _solid("#ff0000"))
    c.rotate_top()
    assert (c._top.width(), c._top.height()) == (60, 120)
    # After a clockwise/right rotation the bottom-left quadrant becomes the
    # top-left one (blue originally) and the top-left one becomes the
    # top-right one (red originally).
    _expect_corners(c, "#0000ff", "#ff0000")
    assert c._bottom.width() == 100  # bottom layer stays untouched
    assert c._bottom.height() == 100


def test_flip_top_keeps_size_and_swaps_pixels(canvas):
    """Flip preserves the dimensions while mirroring the source pixels."""
    c = OverlayCanvas()
    c.set_pixmaps(_quadrants(w=120, h=60), _solid("#ff0000"))
    c.flip_top(horizontal=True)
    assert (c._top.width(), c._top.height()) == (120, 60)
    # Horizontal flip mirrors the columns: the green block becomes the
    # top-left quadrant and the red block the top-right one.
    _expect_corners(c, "#00ff00", "#ff0000")
    c.flip_top(horizontal=False)
    # Vertical flip swaps the rows: the whole bottom row moves to the top,
    # so the top-left becomes the original yellow block and the top-right
    # the original blue block.
    _expect_corners(c, "#ffff00", "#0000ff")
    assert c._bottom.toImage().pixelColor(0, 0).name() == "#ff0000"


def test_rotate_top_resets_its_view_but_not_bottom(canvas):
    """Transformations reset only the affected top-layer view state."""
    c = OverlayCanvas()
    c.set_pixmaps(_quadrants(), _solid("#ff0000"))
    c._top_state.zoom = 3.0
    c._top_state.offset = QPointF(10, 20)
    c._bottom_state.zoom = 2.0
    c.rotate_top()
    assert c._top_state.zoom == 1.0
    assert c._top_state.offset.isNull()
    assert c._bottom_state.zoom == 2.0


def test_transformed_top_survives_swap(canvas):
    """A rotated layer carries its rotation when swapped to the bottom."""
    c = OverlayCanvas()
    c.set_pixmaps(_quadrants(), _solid("#ff0000"))
    c.rotate_top()
    assert (c._top.width(), c._top.height()) == (60, 120)
    c.swap_layers()
    assert (c._top.width(), c._top.height()) == (100, 100)
    assert (c._bottom.width(), c._bottom.height()) == (60, 120)


def test_rotate_top_ignored_when_layer_null():
    """Transformations on an empty canvas must be a safe no-op."""
    c = OverlayCanvas()
    c.rotate_top()
    c.flip_top()
    assert c._top.isNull() and c._bottom.isNull()


def test_context_menu_build_wires_rotate_flip_and_fit(canvas):
    """The context menu wires the Rotate/Flip submenus and Fit 1:1."""
    from bagheeraview.core import constants

    canvas.set_pixmaps(_quadrants(), _solid("#ff0000"))

    menu = canvas._build_context_menu()
    try:
        actions = [a for a in menu.actions() if not a.isSeparator()]
        texts = [a.text() for a in actions]
        assert texts == [
            constants.UITexts.VIEWER_MENU_ROTATE,
            constants.UITexts.VIEWER_MENU_FLIP,
            constants.UITexts.DUPLICATE_OVERLAY_FIT_1_1,
        ]

        rotate_menu = actions[0].menu()
        flip_menu = actions[1].menu()
        rotate_left, rotate_right = rotate_menu.actions()
        flip_h, flip_v = flip_menu.actions()
        fit_action = actions[2]

        assert rotate_left.text() == constants.UITexts.VIEWER_MENU_ROTATE_LEFT
        assert rotate_right.text() == constants.UITexts.VIEWER_MENU_ROTATE_RIGHT
        assert flip_h.text() == constants.UITexts.VIEWER_MENU_FLIP_H
        assert flip_v.text() == constants.UITexts.VIEWER_MENU_FLIP_V
        assert fit_action.text() == constants.UITexts.DUPLICATE_OVERLAY_FIT_1_1

        # The actions are connected to the real canvas transformations.
        rotate_left.trigger()
        assert (canvas._top.width(), canvas._top.height()) == (60, 120)
        rotate_left.trigger()
        assert (canvas._top.width(), canvas._top.height()) == (120, 60)
        # After two left rotations the top row is yellow|blue and the bottom
        # row green|red (a half-turn of the original).
        _expect_corners(canvas, "#ffff00", "#0000ff")
        flip_h.trigger()
        # Horizontal mirror swaps the columns: blue|yellow on the top row and
        # red|green on the bottom row.
        _expect_corners(canvas, "#0000ff", "#ffff00")
        flip_v.trigger()
        # Vertical mirror swaps the rows: red|green return to the top row.
        _expect_corners(canvas, "#ff0000", "#00ff00")

        # Fit 1:1 action must switch the zoom exactly like the double click.
        before = canvas._bottom_state.zoom
        fit_action.trigger()
        assert abs(canvas._fit_scale(canvas._bottom) *
                   canvas._bottom_state.zoom - 1.0) < 1e-6
        fit_action.trigger()
        assert canvas._bottom_state.zoom == before
    finally:
        menu.deleteLater()
