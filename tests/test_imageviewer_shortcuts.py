import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from bagheeraview.core.app import AppShortcutController
from bagheeraview.core.imageviewer import ImageViewer
from bagheeraview.core.imagescanner import generate_thumbnail


class ShortcutMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.viewer_shortcuts = {}
        self.dialog_shortcuts = {}
        self.loaded_global_shortcuts = None
        self.saved_layout = False
        self.loaded_layout = False
        self.save_count = 0
        self.load_count = 0
        for name in (
                "load_more_images", "load_all_images", "save_layout",
                "load_layout_dialog", "open_current_folder",
                "delete_current_image", "hard_refresh_content",
                "refresh_content", "select_all_thumbnails",
                "select_none_thumbnails", "invert_selection_thumbnails"):
            setattr(self, name, lambda *args, **kwargs: None)
        self.save_layout = self._save_layout
        self.load_layout_dialog = self._load_layout

    def _save_layout(self):
        self.saved_layout = True
        self.save_count += 1

    def _load_layout(self):
        self.loaded_layout = True
        self.load_count += 1


class ShortcutTestViewer(ImageViewer):
    def __init__(self, main_win):
        QWidget.__init__(self)
        self.main_win = main_win
        self.shortcuts = {}
        self.panes = []
        self.active_pane = None

    def reset_inactivity_timer(self):
        pass

    def update_highlight(self):
        pass


def test_save_and_load_layout_shortcuts_work_with_hidden_main_window():
    app = QApplication.instance() or QApplication([])
    main_window = ShortcutMainWindow()
    controller = AppShortcutController(main_window)
    main_window.shortcut_controller = controller
    viewer = ShortcutTestViewer(main_window)

    main_window.hide()
    viewer.show()
    viewer.setFocus()
    QTest.keyClick(viewer, Qt.Key_S)
    QTest.keyClick(viewer, Qt.Key_L)

    assert not main_window.isVisible()
    assert main_window.saved_layout
    assert main_window.loaded_layout
    assert main_window.save_count == 1
    assert main_window.load_count == 1

    viewer.hide()
    viewer.deleteLater()
    main_window.close()
    app.processEvents()


def test_tiff_thumbnail_reader_closes_before_its_qfile(tmp_path):
    source = tmp_path / "source.tiff"
    image = QImage(32, 24, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.blue)
    assert image.save(str(source), "TIFF")

    fd = os.open(source, os.O_RDONLY)
    try:
        thumbnail = generate_thumbnail(str(source), 16, fd=fd)
    finally:
        os.close(fd)

    assert thumbnail is not None
    assert not thumbnail.isNull()
    assert thumbnail.width() <= 16
    assert thumbnail.height() <= 16
