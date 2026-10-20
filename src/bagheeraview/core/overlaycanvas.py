"""
Overlay Canvas Module for Bagheera.

This module implements the OverlayCanvas, a high-performance widget used by
the duplicate management dialog to compare two images through advanced
overlay visualization modes (toggle, split, pixel difference and opacity).

The widget renders both layers with a single QPainter pass inside a custom
paintEvent. A repaint timer coalesces rapid input events so the frame rate
stays fluid, and a reduced-quality cached version of each layer is used while
the user is interacting (panning or zooming), switching back to full detail
shortly after the interaction ends.

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


class OverlayCanvas(QWidget):
    """
    Renders two pixmaps on top of each other in one of four comparison modes.

    The bottom layer defines the reference geometry. By default the top layer
    is scaled so that it aligns pixel-perfectly with the bottom layer (its
    width is stretched to the bottom layer width), and shares the common view
    zoom and offset. It additionally supports an independent zoom multiplier
    and offset (pan) that can be reset to the aligned default with reset_view.
    """

    MODE_TOGGLE = 0
    MODE_SPLIT = 1
    MODE_DIFFERENCE = 2
    MODE_OPACITY = 3

    # Emitted whenever the top layer zoom or position changes so that the
    # dialog can keep status widgets in sync.
    transform_changed = Signal()

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

        self._view_zoom = 1.0
        self._view_offset = QPointF(0.0, 0.0)
        self._top_zoom_mul = 1.0
        self._top_offset = QPointF(0.0, 0.0)

        self._dragging_split = False
        self._dragging_pan = None  # Either "view", "top" or None
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
        Sets the two layers to display and resets the view to the aligned
        default state.

        Args:
            top (QPixmap): Image displayed as the top layer.
            bottom (QPixmap): Image displayed as the bottom layer.
        """
        self._top = top if top is not None else QPixmap()
        self._bottom = bottom if bottom is not None else QPixmap()
        self._top_small = self._make_small(self._top)
        self._bottom_small = self._make_small(self._bottom)
        self.reset_view()

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
        self.update()

    def swap_layers(self):
        """
        Swaps the top and bottom layers and resets the top layer transform
        so the newly swapped-in top layer returns to its aligned default.
        """
        self._top, self._bottom = self._bottom, self._top
        self._top_small, self._bottom_small = self._bottom_small, self._top_small
        self._top_zoom_mul = 1.0
        self._top_offset = QPointF(0.0, 0.0)
        self.update()

    def reset_view(self):
        """
        Resets the common view and the top layer transform to their default
        aligned state (fit to widget size, top layer aligned with bottom).
        """
        self._view_zoom = self._fit_zoom()
        self._view_offset = QPointF(0.0, 0.0)
        self._top_zoom_mul = 1.0
        self._top_offset = QPointF(0.0, 0.0)
        self.update()

    def toggle_fit_actual(self):
        """
        Toggles between fitting the image to the widget and 1:1 actual size.
        """
        if abs(self._view_zoom - 1.0) < 0.01:
            self._view_zoom = self._fit_zoom()
        else:
            self._view_zoom = 1.0
        self.update()

    def zoom_view(self, factor):
        """
        Zooms the common view by the given factor, centered on the widget.

        Args:
            factor (float): Zoom multiplier (e.g. 1.1 to zoom in).
        """
        self._view_zoom = max(1e-6, self._view_zoom * factor)
        self.update()

    def zoom_top(self, factor):
        """
        Zooms only the top layer by the given factor.

        Args:
            factor (float): Zoom multiplier for the top layer.
        """
        self._top_zoom_mul = max(1e-6, self._top_zoom_mul * factor)
        self.transform_changed.emit()
        self.update()

    # --- Rendering ------------------------------------------------------

    def _fit_zoom(self):
        """
        Calculates the zoom factor that fits the bottom layer in the widget.

        Returns:
            float: The fit zoom factor (1.0 if no layer is available).
        """
        if self._bottom.isNull():
            return 1.0
        w, h = self.width(), self.height()
        if w <= 1 or h <= 1:
            return 1.0
        return min(w / self._bottom.width(), h / self._bottom.height())

    def _layer_rect(self, pixmap, is_top):
        """
        Computes the destination rectangle for one layer in widget coordinates.

        The bottom layer is drawn centered with the common zoom and offset.
        The top layer is stretched to the bottom layer width by default, so
        its own zoom multiplier and offset apply on top of that alignment.

        Args:
            pixmap (QPixmap): The layer to place (used for dimensions).
            is_top (bool): Whether this is the top layer.

        Returns:
            QRectF: Destination rectangle.
        """
        if is_top:
            base = 1.0
            if not self._bottom.isNull() and not pixmap.isNull():
                base = self._bottom.width() / float(pixmap.width())
            zoom = self._view_zoom * base * self._top_zoom_mul
            offset = self._view_offset + self._top_offset
        else:
            zoom = self._view_zoom
            offset = self._view_offset

        w = pixmap.width() * zoom
        h = pixmap.height() * zoom
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        top_left = QPointF(center.x() - w / 2.0 + offset.x(),
                           center.y() - h / 2.0 + offset.y())
        return QRectF(top_left.x(), top_left.y(), w, h)

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

    def _draw_layer(self, painter, pixmap, small_pixmap, is_top):
        """
        Draws a single layer, clipping the source to the destination rect.

        Args:
            painter (QPainter): The active painter.
            pixmap (QPixmap): Full-size layer.
            small_pixmap (QPixmap): Cached reduced-size version.
            is_top (bool): Whether this is the top layer.
        """
        if pixmap.isNull():
            return
        target = self._layer_rect(pixmap, is_top).intersected(
            QRectF(self.rect()))
        if target.isEmpty():
            return
        source = QRectF(0.0, 0.0, pixmap.width(), pixmap.height())
        if self._interacting and not small_pixmap.isNull():
            painter.drawPixmap(target, small_pixmap, source)
        else:
            painter.drawPixmap(target, pixmap, source)

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

        # Smooth only when zooming out; zoom in / 1:1 needs crisp pixels.
        effective_zoom = self._view_zoom * self._top_zoom_mul
        smooth = effective_zoom < 1.0
        painter.setRenderHint(QPainter.SmoothPixmapTransform, smooth)

        if self._mode == self.MODE_TOGGLE:
            if self._show_top:
                self._draw_layer(painter, self._top, self._top_small, True)
            else:
                self._draw_layer(painter, self._bottom, self._bottom_small,
                                 False)
        elif self._mode == self.MODE_OPACITY:
            self._draw_layer(painter, self._bottom, self._bottom_small, False)
            painter.save()
            painter.setOpacity(self._opacity)
            self._draw_layer(painter, self._top, self._top_small, True)
            painter.restore()
        elif self._mode == self.MODE_SPLIT:
            self._draw_layer(painter, self._bottom, self._bottom_small, False)
            split_x = self.width() * self._split
            painter.save()
            painter.setClipRect(QRectF(0.0, 0.0, split_x, self.height()))
            self._draw_layer(painter, self._top, self._top_small, True)
            painter.restore()
            self._draw_split_handle(painter, split_x)
        else:  # MODE_DIFFERENCE
            self._draw_layer(painter, self._bottom, self._bottom_small, False)
            painter.setCompositionMode(QPainter.CompositionMode_Difference)
            self._draw_layer(painter, self._top, self._top_small, True)
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

    # --- Mouse interaction --------------------------------------------

    def wheelEvent(self, event):
        """
        Zooms the common view (or the top layer with Shift) around the cursor.

        Args:
            event (QWheelEvent): The wheel event.
        """
        if self._bottom.isNull():
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = _ZOOM_STEP if delta > 0 else 1.0 / _ZOOM_STEP

        pos = event.position()
        if event.modifiers() & Qt.ShiftModifier:
            self.zoom_top(factor)
        else:
            # Keep the pixel under the cursor stable while zooming.
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
            offset_to_cursor = pos - anchor
            self._view_zoom = max(1e-6, self._view_zoom * factor)
            self._view_offset += offset_to_cursor * (factor - 1.0)
        self._begin_interaction()
        self._schedule_update()
        event.accept()

    def mousePressEvent(self, event):
        """
        Starts a drag for the split handle, common pan or top layer pan.

        The top layer is panned with Alt+left button or the middle button.

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
            if event.modifiers() & Qt.AltModifier:
                self._dragging_pan = "top"
            else:
                self._dragging_pan = "view"
            self._last_pos = pos
            self._begin_interaction()
            event.accept()
        elif event.button() == Qt.MiddleButton:
            self._dragging_pan = "top"
            self._last_pos = pos
            self._begin_interaction()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Updates the split position or the pan offset while dragging, and
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
            elif self._dragging_pan == "view":
                self._view_offset += delta
                self._schedule_update()
            elif self._dragging_pan == "top":
                self._top_offset += delta
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
        any_drag = self._dragging_split or self._dragging_pan is not None
        self._dragging_split = False
        self._dragging_pan = None
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
        Recomputes the fit zoom when the widget is resized if the view was
        previously in fit state.

        Args:
            event (QResizeEvent): The resize event.
        """
        was_fit = self._view_zoom <= self._fit_zoom() + 1e-9 and \
            self._view_offset.isNull()
        super().resizeEvent(event)
        if was_fit and not self._bottom.isNull():
            self._view_zoom = self._fit_zoom()

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
