import pytest
from PySide6.QtCore import QEvent, QItemSelectionModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QListView, QMainWindow

from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import DEFAULT_VIEWER_SHORTCUTS, VIEWER_ACTIONS
from bagheeraview.core.imagecontroller import ImageController
from bagheeraview.core.imageviewer import rating_menu_label
from bagheeraview.core import imagecontroller


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_rating_shortcuts_are_configurable_actions():
    for rating in range(1, 10):
        assert DEFAULT_VIEWER_SHORTCUTS[f"rating_{rating}"] == (
            getattr(Qt, f"Key_{rating}"), Qt.NoModifier)
        assert f"rating_{rating}" in VIEWER_ACTIONS
    assert DEFAULT_VIEWER_SHORTCUTS["rating_10"] == (
        Qt.Key_0, Qt.NoModifier)
    assert DEFAULT_VIEWER_SHORTCUTS["delete_rating"] == (
        Qt.Key_0, Qt.ControlModifier)
    assert "delete_rating" in VIEWER_ACTIONS


def test_rating_menu_labels_use_half_and_full_stars(qapp):
    assert rating_menu_label(1) == "½☆☆☆☆"
    assert rating_menu_label(2) == "★☆☆☆☆"
    assert rating_menu_label(10) == "★★★★★"


def test_image_controller_sets_and_deletes_rating(qapp, monkeypatch):
    saved = []
    monkeypatch.setattr(
        imagecontroller.XattrManager, "set_attribute",
        lambda path, name, value: saved.append((path, name, value)))
    controller = ImageController(["image.jpg"], 0, initial_tags=["tag"])
    controller.get_current_path = lambda: "image.jpg"
    updates = []
    controller.metadata_changed.connect(
        lambda path, metadata: updates.append((path, metadata)))

    try:
        controller.set_rating(10)
        controller.set_rating(None)
    finally:
        controller.cleanup()

    assert [entry[2] for entry in saved] == ["10", None]
    assert [update[1]["rating"] for update in updates] == [10, 0]


def test_configured_rating_shortcuts_work_in_thumbnail_view(qapp):
    owner = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(owner)
    owner.thumbnail_view = QListView(owner)
    owner._thumbnail_viewport = owner.thumbnail_view.viewport()
    owner.viewer_shortcuts = {
        (Qt.Key_5, Qt.NoModifier): ("rating_5", "Set rating to 5"),
        (Qt.Key_0, Qt.ControlModifier): ("delete_rating", "Delete rating"),
    }
    activated = []
    owner.set_selected_rating = activated.append
    model = QStandardItemModel(owner)
    model.appendRow(QStandardItem("thumbnail"))
    owner.thumbnail_view.setModel(model)
    owner.thumbnail_view.setCurrentIndex(model.index(0, 0))
    owner.thumbnail_view.selectionModel().select(
        model.index(0, 0), QItemSelectionModel.Select)
    MainWindow._setup_thumbnail_rating_shortcuts(owner)

    for key, modifiers in (
            (Qt.Key_5, Qt.NoModifier),
            (Qt.Key_0, Qt.ControlModifier)):
        event = QKeyEvent(QEvent.KeyPress, key, modifiers)
        assert MainWindow.eventFilter(owner, owner._thumbnail_viewport, event)

    assert activated == [5, None]
