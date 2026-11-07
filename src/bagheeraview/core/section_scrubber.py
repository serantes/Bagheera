from bisect import bisect_right

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QAbstractItemView, QToolTip, QWidget


def build_sections(keys, label_fn=str):
    """Build contiguous (label, first_row, count) sections from ordered keys."""
    sections = []
    for row, key in enumerate(keys):
        if not sections or sections[-1][3] != key:
            sections.append([label_fn(key), row, 1, key])
        else:
            sections[-1][2] += 1
    return [(label, row, count) for label, row, count, _key in sections]


class SectionScrubber(QWidget):
    """A compact timeline for jumping between sections in an item view."""

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self._view = view
        self._sections = []
        self._tooltips = []
        self._rows = []
        self._total = 1
        self._current = 0
        self._pos_row = 0
        self.setFixedWidth(64)
        self.setMouseTracking(True)
        view.verticalScrollBar().valueChanged.connect(self._sync_from_view)

    def set_sections(self, sections, tooltips=None):
        self._sections = sections
        self._tooltips = list(tooltips) if tooltips is not None else [
            section[0] for section in sections
        ]
        self._rows = [section[1] for section in sections]
        self._total = max(1, sum(section[2] for section in sections))
        self._sync_from_view()
        self.update()

    def _jump(self, y):
        if not self._sections:
            return
        section_index = self._section_index_at_y(y)
        section_row = self._sections[section_index][1]
        index = self._view.model().index(section_row, 0)
        if index.isValid():
            self._view.scrollTo(
                index, QAbstractItemView.ScrollHint.PositionAtTop)

    def _section_index_at_y(self, y):
        fraction = max(0.0, min(1.0, y / max(1, self.height())))
        row = fraction * self._total
        return max(0, bisect_right(self._rows, row) - 1)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip and self._sections:
            section_index = self._section_index_at_y(event.pos().y())
            QToolTip.showText(
                event.globalPos(), self._tooltips[section_index], self)
            event.accept()
            return True
        return super().event(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._jump(event.position().y())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._jump(event.position().y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _first_visible_index(self):
        viewport = self._view.viewport()
        width = viewport.width()
        if width <= 0:
            return self._view.indexAt(QPoint(8, 8))

        step = max(1, width // 12)
        for y in (2, min(18, max(2, viewport.height() - 1))):
            visible = [
                self._view.indexAt(QPoint(x, y))
                for x in range(2, width, step)
            ]
            visible = [index for index in visible if index.isValid()]
            if visible:
                return min(visible, key=lambda index: index.row())
        return self._view.indexAt(QPoint(8, 8))

    def _sync_from_view(self, _value=None):
        if not self._sections:
            return
        index = self._first_visible_index()
        if not index.isValid():
            return
        self._pos_row = index.row()
        self._current = max(0, bisect_right(self._rows, index.row()) - 1)
        self.update()

    def paintEvent(self, _event):
        if not self._sections:
            return

        painter = QPainter(self)
        palette = self.palette()
        font = painter.font()
        font.setPointSize(max(6, font.pointSize() - 2))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        height = self.height()
        last_label_y = -10_000

        for section_index, (label, row, _count) in enumerate(self._sections):
            y = int(row / self._total * height)
            painter.setPen(palette.color(QPalette.ColorRole.Mid))
            painter.drawLine(self.width() - 10, y, self.width() - 2, y)

            if y - last_label_y >= metrics.height() + 2:
                role = QPalette.ColorRole.WindowText if \
                    section_index == self._current \
                    else QPalette.ColorRole.PlaceholderText
                painter.setPen(palette.color(role))
                text = metrics.elidedText(
                    label, Qt.TextElideMode.ElideRight, self.width() - 14)
                painter.drawText(
                    QRect(2, y, self.width() - 14, metrics.height()),
                    Qt.AlignmentFlag.AlignRight |
                    Qt.AlignmentFlag.AlignVCenter,
                    text)
                last_label_y = y

        marker_y = int(self._pos_row / self._total * height)
        painter.fillRect(
            0, marker_y, self.width(), 2,
            palette.color(QPalette.ColorRole.Highlight))
