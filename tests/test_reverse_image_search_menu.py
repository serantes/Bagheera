from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QMenu

from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import UITexts
from bagheeraview.core.imageviewer import ImageViewer


def test_reverse_image_search_menu_actions_select_expected_engines():
    app = QApplication.instance() or QApplication([])
    search = Mock()
    owner = SimpleNamespace(open_reverse_image_search=search)
    menu = QMenu()

    MainWindow.populate_reverse_image_search_submenu(
        owner, menu, "/tmp/image.png")

    actions = menu.actions()
    assert [action.text() for action in actions] == [
        UITexts.REVERSE_IMAGE_SEARCH_ALL,
        "",
        UITexts.REVERSE_IMAGE_SEARCH_BING,
        UITexts.REVERSE_IMAGE_SEARCH_GOOGLE,
        UITexts.REVERSE_IMAGE_SEARCH_TINEYE,
        UITexts.REVERSE_IMAGE_SEARCH_YANDEX,
    ]

    actions[0].trigger()
    actions[2].trigger()
    actions[3].trigger()
    actions[4].trigger()
    actions[5].trigger()

    assert search.call_args_list == [
        (("/tmp/image.png",), {}),
        (("/tmp/image.png",), {"engines": ["bing"]}),
        (("/tmp/image.png",), {"engines": ["google"]}),
        (("/tmp/image.png",), {"engines": ["tineye"]}),
        (("/tmp/image.png",), {"engines": ["yandex"]}),
    ]
    menu.deleteLater()
    app.processEvents()


def test_viewer_reverse_search_submenu_uses_current_image():
    app = QApplication.instance() or QApplication([])
    path = "/tmp/current.png"
    main_window = Mock()
    viewer = SimpleNamespace(
        main_win=main_window,
        controller=SimpleNamespace(get_current_path=Mock(return_value=path)),
    )
    menu = QMenu()

    ImageViewer._populate_reverse_image_search_menu(viewer, menu)

    main_window.populate_reverse_image_search_submenu.assert_called_once_with(
        menu, path)
    menu.deleteLater()
    app.processEvents()
