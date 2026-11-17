from types import SimpleNamespace

from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import app as app_module
from bagheeraview.core import imageviewer
from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import UITexts


def test_filter_replacement_resizes_viewer(monkeypatch, tmp_path):
    qapp = QApplication.instance() or QApplication([])

    class Screen:
        def availableGeometry(self):
            return QRect(0, 0, 800, 600)

    screen = Screen()
    monkeypatch.setattr(imageviewer.ImageViewer, "inhibit_screensaver", lambda _: None)
    monkeypatch.setattr(imageviewer.ImageViewer, "uninhibit_screensaver", lambda _: None)
    monkeypatch.setitem(imageviewer.APP_CONFIG, "viewer_auto_resize_window", True)

    old_path = tmp_path / "old.png"
    new_path = tmp_path / "new.png"
    assert QPixmap(100, 75).save(str(old_path))
    assert QPixmap(4000, 3000).save(str(new_path))

    viewer = imageviewer.ImageViewer(
        None, [str(old_path), str(new_path)], 0, first_load=False)
    viewer.screen = lambda: screen
    viewer.resize(200, 150)
    viewer.show()
    qapp.processEvents()
    initial_size = viewer.size()

    window = SimpleNamespace(
        viewers=[viewer],
        _known_paths={str(old_path), str(new_path)},
        found_items_data=[],
    )

    MainWindow.update_viewers_filter(window, [str(new_path)])
    qapp.processEvents()

    assert viewer.controller.get_current_path() == str(new_path)
    assert viewer.size().width() > initial_size.width()
    assert viewer.size().height() > initial_size.height()
    viewer.close()


def test_filter_replacement_after_naming_face(monkeypatch, tmp_path):
    qapp = QApplication.instance() or QApplication([])
    monkeypatch.setattr(imageviewer.ImageViewer, "inhibit_screensaver", lambda _: None)
    monkeypatch.setattr(imageviewer.ImageViewer, "uninhibit_screensaver", lambda _: None)
    monkeypatch.setattr(imageviewer.ImageViewer, "_update_person_recognition_for_face",
                        lambda *_args: None)
    monkeypatch.setitem(imageviewer.APP_CONFIG, "viewer_auto_resize_window", True)

    old_path = tmp_path / "old.png"
    new_path = tmp_path / "new.png"
    assert QPixmap(300, 200).save(str(old_path))
    assert QPixmap(4000, 3000).save(str(new_path))
    viewer = imageviewer.ImageViewer(
        None, [str(old_path), str(new_path)], 0, first_load=False)
    viewer.show()
    QTest.qWait(200)
    initial_size = viewer.size()
    window = SimpleNamespace(
        viewers=[viewer],
        _known_paths={str(old_path), str(new_path)},
        found_items_data=[],
        filmstrip_position="bottom",
        is_wayland=False,
        isVisible=lambda: True,
        face_names_history=[],
        tag_edit_widget=SimpleNamespace(available_tags=["Person/Test"]),
    )
    window.update_metadata_for_path = lambda *_args: (
        MainWindow.update_viewers_filter(window, [str(new_path)]))
    viewer.main_win = window
    viewer.active_pane.main_win = window
    viewer.controller.show_regions = True
    monkeypatch.setattr(viewer.controller, "save_regions", lambda: None)

    dialogs = []

    def accept_name():
        dialog = qapp.activeModalWidget()
        dialogs.append(dialog)
        if isinstance(dialog, imageviewer.FaceNameDialog):
            dialog.name_input.name_to_tags_map["Test"] = ["Person/Test"]
            dialog.name_input.name_combo.setEditText("Test")
            QTest.keyClick(dialog.name_input.name_combo.lineEdit(), Qt.Key_Return)

    QTimer.singleShot(100, accept_name)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(
        lambda: qapp.activeModalWidget().reject()
        if qapp.activeModalWidget() else None)
    timeout.start(1500)
    canvas = viewer.canvas
    canvas.drawing = True
    canvas.drawing_button = Qt.LeftButton
    canvas.current_rect = QRect(20, 20, 80, 80)
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(100, 100))
    timeout.stop()
    QTest.qWait(500)

    try:
        assert len(dialogs) == 1
        assert isinstance(dialogs[0], imageviewer.FaceNameDialog)
        assert viewer.controller.get_current_path() == str(new_path)
        assert viewer.size().width() > initial_size.width()
        assert viewer.size().height() > initial_size.height()
        assert viewer.scroll_area.viewport().width() >= viewer.canvas.width()
        assert viewer.scroll_area.viewport().height() >= viewer.canvas.height()
    finally:
        viewer.close()
        qapp.processEvents()


def test_filter_counts_only_visible_and_total_images():
    filter_mode = SimpleNamespace(isChecked=lambda: True)
    window = SimpleNamespace(
        tags_list=SimpleNamespace(rowCount=lambda: 0),
        filter_mode_group=SimpleNamespace(buttons=lambda: [filter_mode]),
        is_cleaning=False,
        _suppress_updates=False,
        get_selected_paths=lambda: [],
        proxy_model=SimpleNamespace(
            include_tags=set(),
            exclude_tags=set(),
            name_filter="",
            excluded_extensions=set(),
            match_mode="AND",
            prepare_filter=lambda: None,
            invalidate=lambda: None,
            rowCount=lambda: 6,
        ),
        filter_name_input=SimpleNamespace(text=lambda: "sun"),
        _extension_checkboxes={},
        _visible_paths_cache=None,
        get_visible_image_paths=lambda: ["/photos/sun1.jpg", "/photos/sun2.jpg",
                                         "/photos/sun3.jpg"],
        get_all_image_paths=lambda: ["/photos/sun1.jpg", "/photos/sun2.jpg",
                                     "/photos/sun3.jpg", "/photos/other.jpg"],
        filter_stats_lbl=SimpleNamespace(setText=lambda text: setattr(
            window.filter_stats_lbl, "text", text)),
        filtered_count_lbl=SimpleNamespace(setText=lambda text: setattr(
            window.filtered_count_lbl, "text", text)),
        restore_selection=lambda paths: None,
        update_viewers_filter=lambda paths: setattr(
            window, "visible_paths_sent_to_viewers", paths),
    )

    MainWindow.apply_filters(window)

    assert window.filtered_count_lbl.text == UITexts.FILTERED_COUNT.format(3)
    assert window.filter_stats_lbl.text == UITexts.FILTER_STATS_HIDDEN.format(1, 3)
    assert window.visible_paths_sent_to_viewers == [
        "/photos/sun1.jpg",
        "/photos/sun2.jpg",
        "/photos/sun3.jpg",
    ]
