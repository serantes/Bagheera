"""
Overlay Canvas Module for Bagheera.

This module implements the OverlayCanvas, a high-performance widget used by
the duplicate management dialog to compare two images through advanced
overlay visualization modes (toggle, split, pixel difference and opacity).

The widget renders both layers with a single QPainter pass inside a custom
paintEvent. Each layer keeps an independent zoom (relative to its own
fit-to-window scale) and pan offset, so either image can be inspected on its
own. A repaint timer coalesces rapid input events so the frame rate stays
fluid, and a reduced-quality cached version of each layer is used while the
user is interacting, switching back to full detail shortly afterwards.

Classes:
    OverlayCanvas: A widget rendering two pixmaps in overlay comparison modes.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPen, QPixmap
)
from PySide6.QtWidgets import QWidget

from .constants import UITexts

# Maximum width of the cached reduced-size version of a layer.
_MAX_CACHE_SIZE = 2048
# Coalescing interval for repaints, in milliseconds.
_REPAINT_INTERVAL_MS = 16
# Delay, in milliseconds, before a full-quality repaint after interaction.
_FULL_QUALITY_DELAY_MS = 80
# Drag threshold (pixels) to grab the split handle.
_SPLIT_HANDLE_DISTANCE = 8
# Zoom factor applied per wheel notch.
_ZOOM_STEP = 1.1
# Minimum and maximum absolute scale (image pixels per screen pixel).
_MIN_SCALE = 0.01
_MAX_SCALE = 64.0

LAYER_TOP = "top"
LAYER_BOTTOM = "bottom"
LAYER_BOTH = "both"


def _clamp_scale(scale):
    """Clamps a scale factor within the allowed zoom range."""
    return max(_MIN_SCALE, min(_MAX_SCALE, scale))


class _LayerState:
    """Independent zoom and pan state of a single overlay layer."""

    def __init__(self):
        # Zoom relative to the layer's own fit-to-window scale (1.0 = fit).
        self.zoom = 1.0
        # Pan offset in widget pixels from the centered position.
        self.offset = QPointF(0.0, 0.0)

    def reset(self):
        """Restores the default fit and centered state."""
        self.zoom = 1.0
        self.offset = QPointF(0.0, 0.0)


class OverlayCanvas(QWidget):
    """
    Renders two pixmaps on top of each other in one of four comparison modes.

    Each layer owns an independent transform: a zoom relative to its own
    fit-to-window scale and a pan offset in widget pixels. Without modifiers
    wheel and drag move both layers together; Shift restricts them to the top
    layer and Ctrl to the bottom layer.
    """

    MODE_TOGGLE = 0
    MODE_SPLIT = 1
    MODE_DIFFERENCE = 2
    MODE_OPACITY = 3

    # Emitted whenever a layer zoom or position changes so that the dialog
    # can keep status widgets in sync.
    transform_changed = Signal()
    # Emitted when the visible layer or the layer roles change (toggle or
    # swap), so the dialog can refresh its legend.
    layer_changed = Signal()

    def __init__(self, parent=None):
        """Initializes the canvas with default state and interaction flags."""
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(200, 200)

        self._top = QPixmap()
        self._bottom = QPixmap()
        self._top_small = QPixmap()
        self._bottom_small = QPixmap()

        self._mode = self.MODE_TOGGLE
        self._show_top = True
        self._opacity = 0.5
        self._split = 0.5
        self._swapped = False

        self._top_state = _LayerState()
        self._bottom_state = _LayerState()

        self._dragging_split = False
        self._drag_targets = None  # One of LAYER_TOP, LAYER_BOTTOM, LAYER_BOTH.
        self._last_pos = None
        self._interacting = False

        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(_REPAINT_INTERVAL_MS)
        self._repaint_timer.timeout.connect(self._flush_repaint)

        self._full_quality_timer = QTimer(self)
        self._full_quality_timer.setSingleShot(True)
        self._full_quality_timer.setInterval(_FULL_QUALITY_DELAY_MS)
        self._full_quality_timer.timeout.connect(self._finish_interaction)

    # --- Public API -----------------------------------------------------

    def set_pixmaps(self, top, bottom):
        """
        Sets the two layers to display and fully resets the overlay state.

        Args:
            top (QPixmap): Image displayed as the top layer.
            bottom (QPixmap): Image displayed as the bottom layer.
        """
        self._top = top if top is not None else QPixmap()
        self._bottom = bottom if bottom is not None else QPixmap()
        self._top_small = self._make_small(self._top)
        self._bottom_small = self._make_small(self._bottom)
        self.reset_all()

    def set_mode(self, mode):
        """
        Changes the active comparison mode.

        Args:
            mode (int): One of the MODE_* constants.
        """
        self._mode = int(mode)
        self.update()

    def set_opacity(self, value):
        """
        Sets the top layer opacity.

        Args:
            value (int or float): Opacity in the 0-100 range.
        """
        self._opacity = max(0.0, min(1.0, float(value) / 100.0))
        self.update()

    def toggle_layer(self):
        """Switches which layer is visible in Toggle mode."""
        self._show_top = not self._show_top
        self.layer_changed.emit()
        self.update()

    def swap_layers(self):
        """
        Swaps the top and bottom images; each image keeps its own transform.
        """
        self._top, self._bottom = self._bottom, self._top
        self._top_small, self._bottom_small = self._bottom_small, self._top_small
        self._top_state, self._bottom_state = self._bottom_state, self._top_state
        self._swapped = not self._swapped
        self.layer_changed.emit()
        self.update()

    def reset_view(self):
        """
        Resets zoom and pan of both layers to their fit, centered default.
        """
        self._top_state.reset()
        self._bottom_state.reset()
        self.update()

    def reset_split(self):
        """Centers the interactive split handle."""
        self._split = 0.5
        self.update()

    def reset_all(self):
        """Resets every piece of overlay state (view, split, opacity, roles)."""
        self._top_state.reset()
        self._bottom_state.reset()
        self._split = 0.5
        self._opacity = 0.5
        self._show_top = True
        self._swapped = False
        self.update()

    def toggle_fit_actual(self):
        """
        Toggles between fit-to-window and real-pixel (1:1) zoom.

        The reference at real-pixel zoom is the layer with the most pixels;
        the other layer is scaled so both cover the same screen rectangle.
        """
        ref = self._reference_for_1x1()
        if ref is None:
            return
        ref_pixmap, ref_state = ref
        if abs(self._fit_scale(ref_pixmap) * ref_state.zoom - 1.0) < 0.01:
            self.reset_view()
            return

        ref_w = ref_pixmap.width()
        for pixmap, state in self._layers():
            state.zoom = (ref_w / float(pixmap.width())) / self._fit_scale(pixmap)
            state.offset = QPointF(0.0, 0.0)
        self.update()

    def zoom_view(self, factor):
        """
        Zooms both layers by the given factor, centered on the widget.

        Args:
            factor (float): Zoom multiplier (e.g. 1.1 to zoom in).
        """
        self.zoom_layers(factor, LAYER_BOTH, None)

    def zoom_layers(self, factor, target=LAYER_BOTH, anchor=None):
        """
        Zooms the affected layers keeping the pixel under ``anchor`` fixed.

        Args:
            factor (float): Zoom multiplier.
            target (str): One of LAYER_TOP, LAYER_BOTTOM, LAYER_BOTH.
            anchor (QPointF, optional): Widget-space zoom anchor; the widget
                center is used when omitted.
        """
        affected = self._states_for(target)
        if not affected:
            return
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        c = anchor - QPointF(self.width() / 2.0, self.height() / 2.0)
        for (pixmap, state) in affected:
            if pixmap.isNull():
                continue
            fit = self._fit_scale(pixmap)
            target_scale = _clamp_scale(fit * state.zoom * factor)
            effective = target_scale / (fit * state.zoom)
            state.zoom = target_scale / fit
            state.offset = c - (c - state.offset) * effective
        self.transform_changed.emit()
        self.update()

    # --- Read-only state helpers -----------------------------------------

    @property
    def is_swapped(self):
        """True when the top/bottom roles have been swapped."""
        return self._swapped

    @property
    def shows_top(self):
        """True when Toggle mode currently displays the top layer."""
        return self._show_top

    @property
    def split(self):
        """Relative position of the split handle (0.0 to 1.0)."""
        return self._split
# --- Rendering ------------------------------------------------------

    def _fit_scale(self, pixmap):
        """
        Calculates the scale that fits the pixmap inside the widget.

        Args:
            pixmap (QPixmap): The layer used for its dimensions.

        Returns:
            float: The fit scale (1.0 if unavailable).
        """
        if pixmap.isNull():
            return 1.0
        w, h = self.width(), self.height()
        if w <= 1 or h <= 1 or pixmap.width() == 0 or pixmap.height() == 0:
            return 1.0
        return min(w / pixmap.width(), h / pixmap.height())

    def _layers(self):
        """Yields the (pixmap, state) pair for every existing layer."""
        return ((self._top, self._top_state),
                (self._bottom, self._bottom_state))

    def _states_for(self, target):
        """
        Returns the affected (pixmap, state) pairs for a zoom/drag target.

        Args:
            target (str): One of LAYER_TOP, LAYER_BOTTOM, LAYER_BOTH.

        Returns:
            list: The matching (pixmap, state) tuples.
        """
        if target == LAYER_TOP:
            return [(self._top, self._top_state)]
        if target == LAYER_BOTTOM:
            return [(self._bottom, self._bottom_state)]
        return list(self._layers())

    @staticmethod
    def _targets_for(modifiers):
        """
        Maps keyboard modifiers to the manipulated layer(s).

        Shift selects the top layer only, Ctrl the bottom layer only; with
        no modifier both layers move together.

        Args:
            modifiers (Qt.KeyboardModifiers): The active modifiers.

        Returns:
            str: One of LAYER_TOP, LAYER_BOTTOM, LAYER_BOTH.
        """
        if modifiers & Qt.ShiftModifier:
            return LAYER_TOP
        if modifiers & Qt.ControlModifier:
            return LAYER_BOTTOM
        return LAYER_BOTH

    def _reference_for_1x1(self):
        """
        Chooses the reference layer for real-pixel zoom (the largest one).

        Returns:
            tuple or None: (pixmap, state) of the reference layer.
        """
        if self._top.isNull() and self._bottom.isNull():
            return None
        if self._top.isNull():
            return (self._bottom, self._bottom_state)
        if self._bottom.isNull():
            return (self._top, self._top_state)
        top_pixels = self._top.width() * self._top.height()
        bottom_pixels = self._bottom.width() * self._bottom.height()
        if top_pixels >= bottom_pixels:
            return (self._top, self._top_state)
        return (self._bottom, self._bottom_state)

    def _draw_layer(self, painter, pixmap, small_pixmap, state):
        """
        Paints the visible portion of one layer, mapping source pixels to the
        visible screen rectangle without distortion.

        Args:
            painter (QPainter): The active painter.
            pixmap (QPixmap): Full-size layer.
            small_pixmap (QPixmap): Cached reduced-size version.
            state (_LayerState): Independent transform of this layer.
        """
        if pixmap.isNull():
            return
        dest = self._layer_rect(pixmap, state)
        if dest.width() <= 0 or dest.height() <= 0:
            return
        visible = dest.intersected(QRectF(self.rect()))
        if visible.isEmpty():
            return
        sx = pixmap.width() / dest.width()
        sy = pixmap.height() / dest.height()
        src = QRectF((visible.x() - dest.x()) * sx,
                     (visible.y() - dest.y()) * sy,
                     visible.width() * sx, visible.height() * sy)
        scale = self._fit_scale(pixmap) * state.zoom
        painter.setRenderHint(QPainter.SmoothPixmapTransform, scale < 1.0)
        if self._interacting and not small_pixmap.isNull():
            k = small_pixmap.width() / float(pixmap.width())
            painter.drawPixmap(visible, small_pixmap,
                               QRectF(src.x() * k, src.y() * k,
                                      src.width() * k, src.height() * k))
        else:
            painter.drawPixmap(visible, pixmap, src)

    def _layer_rect(self, pixmap, state):
        """
        Computes the destination rectangle of one layer in widget pixels.

        The scale is applied uniformly to both axes, so the aspect ratio of
        the source image is always preserved.

        Args:
            pixmap (QPixmap): The layer being placed.
            state (_LayerState): Its independent transform.

        Returns:
            QRectF: Centered destination rectangle plus the pan offset.
        """
        scale = _clamp_scale(self._fit_scale(pixmap) * state.zoom)
        w = pixmap.width() * scale
        h = pixmap.height() * scale
        center = QPointF(self.width() / 2.0 + state.offset.x(),
                         self.height() / 2.0 + state.offset.y())
        return QRectF(center.x() - w / 2.0, center.y() - h / 2.0, w, h)

    @staticmethod
    def _make_small(pixmap):
        """
        Builds a reduced-size cached copy of a pixmap for fast interaction.

        Args:
            pixmap (QPixmap): The source pixmap.

        Returns:
            QPixmap: Scaled-down pixmap, or an empty pixmap if the source is
            null or already small enough.
        """
        if pixmap.isNull():
            return QPixmap()
        if pixmap.width() <= _MAX_CACHE_SIZE and pixmap.height() <= _MAX_CACHE_SIZE:
            return QPixmap(pixmap)
        return pixmap.scaled(
            _MAX_CACHE_SIZE, _MAX_CACHE_SIZE,
            Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def paintEvent(self, event):
        """
        Paints the current overlay composition in a single painter pass.

        Args:
            event (QPaintEvent): The paint event (unused, the full widget is
                always repainted because WA_OpaquePaintEvent is enabled).
        """
        painter = QPainter(self)
        if self._mode == self.MODE_DIFFERENCE:
            painter.fillRect(self.rect(), Qt.black)
        else:
            painter.fillRect(self.rect(), QColor("#1e1e1e"))

        if self._bottom.isNull():
            painter.setPen(QColor("#bbbbbb"))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             UITexts.FILE_NOT_FOUND)
            return

        if self._mode == self.MODE_TOGGLE:
            if self._show_top:
                self._draw_layer(painter, self._top, self._top_small,
                                 self._top_state)
            else:
                self._draw_layer(painter, self._bottom, self._bottom_small,
                                 self._bottom_state)
        elif self._mode == self.MODE_OPACITY:
            self._draw_layer(painter, self._bottom, self._bottom_small,
                             self._bottom_state)
            painter.save()
            painter.setOpacity(self._opacity)
            self._draw_layer(painter, self._top, self._top_small,
                             self._top_state)
            painter.restore()
        elif self._mode == self.MODE_SPLIT:
            self._draw_layer(painter, self._bottom, self._bottom_small,
                             self._bottom_state)
            split_x = self.width() * self._split
            painter.save()
            painter.setClipRect(QRectF(0.0, 0.0, split_x, self.height()))
            self._draw_layer(painter, self._top, self._top_small,
                             self._top_state)
            painter.restore()
            self._draw_split_handle(painter, split_x)
        else:  # MODE_DIFFERENCE
            self._draw_layer(painter, self._bottom, self._bottom_small,
                             self._bottom_state)
            painter.setCompositionMode(QPainter.CompositionMode_Difference)
            self._draw_layer(painter, self._top, self._top_small,
                             self._top_state)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def _draw_split_handle(self, painter, x):
        """
        Draws the interactive split line and handle knob.

        Args:
            painter (QPainter): The active painter.
            x (float): Horizontal position of the split in widget coordinates.
        """
        line_y0 = 12.0
        line_y1 = self.height() - 12.0

        painter.setPen(QPen(QColor(0, 0, 0, 140), 4.0))
        painter.drawLine(QPointF(x, line_y0), QPointF(x, line_y1))
        painter.setPen(QPen(QColor(255, 255, 255), 2.0))
        painter.drawLine(QPointF(x, line_y0), QPointF(x, line_y1))

        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(QPen(QColor(0, 0, 0), 1.0))
        half = 7.0
        painter.drawEllipse(QPointF(x, (line_y0 + line_y1) / 2.0), half, half)
# --- Mouse interaction ----------------------------------------------

    def wheelEvent(self, event):
        """
        Zooms the affected layers (Shift: top, Ctrl: bottom, none: both)
        around the cursor so the pixel under it stays fixed.

        Args:
            event (QWheelEvent): The wheel event.
        """
        if self._bottom.isNull():
            event.ignore()
            return
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            event.ignore()
            return
        factor = _ZOOM_STEP if delta > 0 else 1.0 / _ZOOM_STEP
        target = self._targets_for(event.modifiers())
        self.zoom_layers(factor, target, event.position())
        self._begin_interaction()
        self._schedule_update()
        event.accept()

    def mousePressEvent(self, event):
        """
        Starts a drag: the split handle in Split mode, or the pan of the
        affected layers (Shift: top, Ctrl: bottom, none: both).

        Args:
            event (QMouseEvent): The mouse press event.
        """
        pos = event.position().toPoint()
        if event.button() == Qt.LeftButton:
            if self._mode == self.MODE_SPLIT:
                split_x = self.width() * self._split
                if abs(pos.x() - split_x) <= _SPLIT_HANDLE_DISTANCE:
                    self._dragging_split = True
                    self._last_pos = pos
                    self._begin_interaction()
                    self._schedule_update()
                    event.accept()
                    return
            self._drag_targets = self._targets_for(event.modifiers())
            self._last_pos = pos
            self._begin_interaction()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Updates the split position or the pan offsets while dragging, and
        refreshes the cursor shape.

        Args:
            event (QMouseEvent): The mouse move event.
        """
        pos = event.position().toPoint()

        if self._last_pos is not None:
            delta = pos - self._last_pos
            if self._dragging_split:
                self._split = max(0.0, min(1.0,
                                           pos.x() / float(self.width())))
                self._schedule_update()
            elif self._drag_targets is not None:
                for (pixmap, state) in self._states_for(self._drag_targets):
                    if not pixmap.isNull():
                        state.offset += delta
                self.transform_changed.emit()
                self._schedule_update()
            self._last_pos = pos

        if self._mode == self.MODE_SPLIT:
            split_x = self.width() * self._split
            if abs(pos.x() - split_x) <= _SPLIT_HANDLE_DISTANCE:
                self.setCursor(Qt.SplitHCursor)
            else:
                self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)

        if event.buttons() == Qt.NoButton:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Ends the active drag and schedules the full-quality repaint.

        Args:
            event (QMouseEvent): The mouse release event.
        """
        any_drag = self._dragging_split or self._drag_targets is not None
        self._dragging_split = False
        self._drag_targets = None
        self._last_pos = None
        if any_drag:
            self._end_interaction()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """
        Toggles between fit to window and 1:1 actual-size zoom.

        Args:
            event (QMouseEvent): The double click event.
        """
        if event.button() == Qt.LeftButton and not self._bottom.isNull():
            self.toggle_fit_actual()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def focusNextPrevChild(self, next):
        """
        Prevents Tab from switching widget focus so it can toggle layers.

        Args:
            next (bool): Direction of the focus traversal.

        Returns:
            bool: Always False, keeping focus inside the canvas.
        """
        return False

    def keyPressEvent(self, event):
        """
        Handles the Tab shortcut used to toggle layers in Toggle mode.

        Args:
            event (QKeyEvent): The key press event.
        """
        if event.key() == Qt.Key_Tab:
            if self._mode == self.MODE_TOGGLE and not self._bottom.isNull():
                self.toggle_layer()
                event.accept()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        """
        Adjusts nothing: the zoom is relative to the per-layer fit, so the
        layers follow the widget size automatically.

        Args:
            event (QResizeEvent): The resize event.
        """
        super().resizeEvent(event)
        self.update()

    # --- Repaint coalescing ----------------------------------------------

    def _begin_interaction(self):
        """Marks the widget as interacting, enabling fast cached layers."""
        self._interacting = True
        self._full_quality_timer.stop()

    def _end_interaction(self):
        """Ends an interaction and schedules the full-quality repaint."""
        self._interacting = False
        self._full_quality_timer.start()

    def _finish_interaction(self):
        """Repaints at full quality after an interaction has finished."""
        self.update()

    def _schedule_update(self):
        """Coalesces paint requests so only one repaint runs per frame."""
        if not self._repaint_timer.isActive():
            self._repaint_timer.start()

    def _flush_repaint(self):
        """Repaints the widget after a coalescing interval."""
        self.update()
