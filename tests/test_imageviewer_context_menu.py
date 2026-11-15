from types import SimpleNamespace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import imageviewer as imageviewer_module
from bagheeraview.core import app as app_module
from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import UITexts
from bagheeraview.core.imageviewer import ImageViewer


@pytest.mark.parametrize("slideshow_running", [False, True])
def test_viewer_context_menu_starts_with_view_and_omits_comparison(
        monkeypatch, slideshow_running):
    app = QApplication.instance() or QApplication([])
    main_window = Mock()
    viewer = SimpleNamespace(
        main_win=main_window,
        controller=SimpleNamespace(
            get_current_path=lambda: "/current/image.png",
            image_list=["/first/image.png", "/current/image.png", "/last/image.png"],
            index=1,
            show_regions=False),
        slideshow_manager=SimpleNamespace(
            is_running=lambda: slideshow_running,
            is_forward=lambda: False,
            is_reverse=lambda: False),
        zoom_manager=SimpleNamespace(toggle_fit_to_screen=Mock()),
        crop_mode=False,
        panes_linked=True,
        movie=None,
        filmstrip=SimpleNamespace(isVisible=lambda: True),
        status_bar_container=SimpleNamespace(isVisible=lambda: True),
        isFullScreen=lambda: False,
        set_slideshow_interval=Mock(),
        _populate_open_with_menu=Mock(),
        _populate_reverse_image_search_menu=Mock(),
    )
    menu_structure = []
    viewer._build_menu_from_data = lambda _menu, items: menu_structure.extend(items)
    viewer._open_current_image_in_viewer = (
        ImageViewer._open_current_image_in_viewer.__get__(viewer))
    monkeypatch.setattr(imageviewer_module, "QMenu", lambda *_args: object())

    ImageViewer._create_viewer_context_menu(viewer)

    assert menu_structure[0]["text"] == UITexts.CONTEXT_MENU_VIEW
    assert menu_structure[1] == "separator"

    def contains_comparison_mode(items):
        return any(
            item.get("text") == UITexts.VIEWER_MENU_COMPARE
            or contains_comparison_mode(item.get("submenu", []))
            for item in items if isinstance(item, dict))

    assert not contains_comparison_mode(menu_structure)
    menu_structure[0]["slot"]()
    main_window.open_viewer_for_paths.assert_called_once_with(
        viewer.controller.image_list, 1)
    app.processEvents()


def test_open_viewer_for_path_preserves_visible_navigation_list():
    paths = ["/first.png", "/current.png", "/last.png"]
    main_window = SimpleNamespace(
        get_visible_image_paths=lambda: paths,
        open_viewer_for_paths=Mock())

    MainWindow.open_viewer_for_path(main_window, "/current.png")

    main_window.open_viewer_for_paths.assert_called_once_with(paths, 1)


def test_open_viewer_for_paths_starts_at_requested_image(monkeypatch):
    paths = ["/first.png", "/current.png", "/last.png"]
    viewer = Mock()
    main_window = SimpleNamespace(
        cache=Mock(),
        viewers=[],
        _setup_viewer_sync=Mock())
    create_viewer = Mock(return_value=viewer)
    monkeypatch.setattr(app_module, "ImageViewer", create_viewer)

    result = MainWindow.open_viewer_for_paths(main_window, paths, 1)

    assert result is viewer
    create_viewer.assert_called_once_with(
        main_window.cache, paths, 1, None, 0, main_window)
    assert main_window.viewers == [viewer]
    main_window._setup_viewer_sync.assert_called_once_with(viewer)
    viewer.show.assert_called_once_with()
