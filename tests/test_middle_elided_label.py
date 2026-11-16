from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

from bagheeraview.core.widgets import MiddleElidedLabel


class _StatusSource(QObject):
    message = Signal(str)


def test_label_elides_and_restores_text_without_expanding_window():
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    layout = QHBoxLayout(window)
    label = MiddleElidedLabel("Ready")
    layout.addWidget(label, 1)
    layout.addWidget(QLabel("Controls"))
    window.resize(320, 80)
    window.show()
    app.processEvents()
    original_width = window.width()

    text = "beginning_" + "long_filename_" * 14 + "ending.jpg"
    source = _StatusSource()
    source.message.connect(label.setText)
    source.message.emit(text)
    app.processEvents()

    rendered = QLabel.text(label)
    assert window.width() == original_width
    assert label.text() == text
    assert rendered.startswith("beginning_")
    assert rendered.endswith("ending.jpg")
    assert "…" in rendered
    assert label.fontMetrics().horizontalAdvance(rendered) <= label.contentsRect().width()

    window.resize(2500, 80)
    app.processEvents()
    assert QLabel.text(label) == text
    window.resize(320, 80)
    app.processEvents()
    assert "…" in QLabel.text(label)

    label.setText("Short.jpg")
    assert QLabel.text(label) == "Short.jpg"
    assert label.text() == "Short.jpg"
    window.close()
