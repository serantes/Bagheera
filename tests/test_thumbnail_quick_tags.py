from collections import deque
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QMenu

from bagheeraview.core import app as app_module
from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import UITexts


def _qt_app():
    return QApplication.instance() or QApplication([])


def test_thumbnail_quick_tags_menu_shows_mru_and_selected_tags(monkeypatch):
    _qt_app()
    tags_by_path = {
        "/images/one.jpg": ["shared", "only-one"],
        "/images/two.jpg": ["shared"],
    }
    monkeypatch.setattr(
        app_module, "load_common_metadata",
        lambda path: SimpleNamespace(tags=tags_by_path[path]))

    window = SimpleNamespace(
        _path_to_model_index={},
        mru_tags=deque(["recent", "shared"]),
    )
    menu = QMenu()
    MainWindow.add_thumbnail_quick_tags_menu(
        window, menu, list(tags_by_path))

    quick_menu = menu.actions()[0].menu()
    assert menu.actions()[0].text() == UITexts.QUICK_TAGS
    actions = {
        action.text(): action
        for action in quick_menu.actions()
        if not action.isSeparator()
    }
    assert actions["recent"].isCheckable()
    assert not actions["recent"].isChecked()
    assert actions["shared"].isChecked()
    assert actions["only-one"].isCheckable()
    assert UITexts.QUICK_TAG_ADD_TAG in actions


def test_thumbnail_quick_tag_applies_to_all_selected_images(monkeypatch):
    written = []
    refreshed = []
    mru = []
    monkeypatch.setattr(
        app_module, "load_common_metadata",
        lambda path: SimpleNamespace(tags=["existing"]))
    monkeypatch.setattr(
        app_module.XattrManager, "set_attribute",
        lambda path, name, value: written.append((path, name, value)))

    window = SimpleNamespace(
        add_to_mru_tags=mru.append,
        update_metadata_for_path=refreshed.append,
    )
    paths = ["/images/one.jpg", "/images/two.jpg"]
    MainWindow.apply_quick_tag_to_selection(window, "new", True, paths)

    assert [(path, value) for path, _name, value in written] == [
        (path, "existing,new") for path in paths
    ]
    assert refreshed == paths
    assert mru == ["new"]
