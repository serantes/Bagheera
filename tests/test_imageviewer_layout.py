from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from bagheeraview.core import imageviewer


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_initial_zoom_accounts_for_controls_before_viewer_is_shown(
        qapp, tmp_path, monkeypatch):
    image_path = tmp_path / "image.png"
    assert QPixmap(32, 24).save(str(image_path))

    viewer = QWidget()
    viewer._first_load = False
    viewer.panes_linked = False
    viewer.filmstrip_position = "bottom"
    viewer.status_bar_container = QWidget(viewer)
    viewer.status_bar_container.setFixedHeight(24)
    viewer.status_bar_container.setVisible(True)
    viewer.filmstrip = QWidget(viewer)
    viewer.filmstrip.setFixedHeight(100)
    viewer.filmstrip.setVisible(True)
    viewer.main_win = SimpleNamespace(
        filmstrip_position="bottom",
        isVisible=lambda: True,
        screen=qapp.primaryScreen,
    )
    zoom_args = []
    controller = SimpleNamespace(
        load_image=lambda: (True, True),
        get_current_path=lambda: str(image_path),
        index=0,
    )
    pane = SimpleNamespace(
        controller=controller,
        movie=None,
        canvas=SimpleNamespace(crop_rect=None),
        reset_inactivity_timer=lambda: None,
        zoom_manager=SimpleNamespace(
            calculate_initial_zoom=lambda *args: zoom_args.append(args)),
    )
    pane.canvas.crop_rect = QRect()
    viewer.active_pane = pane
    viewer.panes = [pane]
    viewer.reset_inactivity_timer = lambda: None
    viewer.update_view = lambda resize_win=False: None
    viewer.sync_filmstrip_selection = lambda _index: None
    monkeypatch.setattr(QTimer, "singleShot", lambda *_args: None)

    assert not viewer.isVisible()
    assert not viewer.status_bar_container.isVisible()
    assert not viewer.filmstrip.isVisible()
    assert not viewer.status_bar_container.isHidden()
    assert not viewer.filmstrip.isHidden()

    imageviewer.ImageViewer.load_and_fit_image_for_pane(viewer, pane)

    screen = qapp.primaryScreen().availableGeometry()
    assert zoom_args == [(
        int(screen.width() * imageviewer.ZOOM_DESKTOP_RATIO),
        int(screen.height() * imageviewer.ZOOM_DESKTOP_RATIO)
        - viewer.filmstrip.height()
        - viewer.status_bar_container.sizeHint().height(),
        False,
    )]


def test_auto_resize_includes_visible_controls_before_viewer_is_shown(
        qapp, monkeypatch):
    class ResizeRecordingWidget(QWidget):
        def resize(self, width, height):
            self.resize_dimensions = (width, height)
            super().resize(width, height)

    viewer = ResizeRecordingWidget()
    viewer.panes = []
    viewer.filmstrip_position = "bottom"
    viewer.status_bar_container = QWidget(viewer)
    viewer.status_bar_container.setFixedHeight(24)
    viewer.status_bar_container.setVisible(True)
    viewer.filmstrip = QWidget(viewer)
    viewer.filmstrip.setFixedHeight(100)
    viewer.filmstrip.setVisible(True)
    viewer.main_win = SimpleNamespace(
        filmstrip_position="bottom",
        isVisible=lambda: True,
        screen=qapp.primaryScreen,
    )
    canvas = QLabel(viewer)
    canvas.setPixmap(QPixmap(200, 100))
    controller = SimpleNamespace(
        get_display_pixmap=lambda: QPixmap(200, 100),
        pixmap_original=QPixmap(200, 100),
        get_current_path=lambda: "image.png",
    )
    pane = SimpleNamespace(controller=controller, canvas=canvas)
    viewer.active_pane = pane
    viewer.panes = [pane]
    viewer.update_title = lambda: None
    viewer.update_status_bar = lambda: None

    monkeypatch.setitem(imageviewer.APP_CONFIG, "viewer_auto_resize_window", True)

    imageviewer.ImageViewer.update_view_for_pane(viewer, pane, resize_win=True)

    assert viewer.resize_dimensions == (
        canvas.width() + imageviewer.VIEWER_FORM_MARGIN,
        canvas.height() + viewer.status_bar_container.sizeHint().height()
        + viewer.filmstrip.height() + imageviewer.VIEWER_FORM_MARGIN,
    )


def test_reused_image_can_resize_window_after_filter_replacement(
        qapp, monkeypatch):
    viewer = QWidget()
    viewer.active_pane = None
    viewer.panes = []
    viewer.isFullScreen = lambda: False
    viewer.reset_inactivity_timer = lambda: None
    updates = []
    viewer.update_view = lambda resize_win=False: updates.append(resize_win)
    viewer.sync_filmstrip_selection = lambda _index: None
    monkeypatch.setattr(QTimer, "singleShot", lambda *_args: None)

    pane = SimpleNamespace(
        controller=SimpleNamespace(
            load_image=lambda: (True, False),
            get_current_path=lambda: "replacement.png",
            index=1,
        ),
        movie=None,
        canvas=SimpleNamespace(setPixmap=lambda _pixmap: None),
        update_view=lambda resize_win=False: updates.append(resize_win),
        reset_inactivity_timer=lambda: None,
    )
    viewer.active_pane = pane
    viewer.panes = [pane]

    imageviewer.ImageViewer.load_and_fit_image_for_pane(
        viewer, pane, resize_win=True)

    assert updates == [True]
