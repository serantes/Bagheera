from unittest.mock import Mock

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QWidget

from bagheeraview.core import similardialog as similar_dialog_module
from bagheeraview.core.constants import UITexts


class FakeMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.cache = Mock()
        self.show_faces = False
        self.open_viewer_for_path = Mock()
        self.populate_open_with_submenu = Mock()


class FakeAction:
    def __init__(self, text="", separator=False):
        self._text = text
        self._separator = separator
        self.triggered = Mock()

    def text(self):
        return self._text

    def isSeparator(self):
        return self._separator

    def setToolTip(self, _text):
        pass

    def setEnabled(self, _enabled):
        pass

    def setCheckable(self, _checkable):
        pass

    def setChecked(self, _checked):
        pass

    def trigger(self):
        for callback in self.triggered.connect.call_args_list:
            callback.args[0]()


class FakeMenu:
    instances = []

    def __init__(self, *_args):
        self._actions = []

    def addAction(self, *args):
        action = FakeAction(str(args[-1]))
        self._actions.append(action)
        return action

    def addMenu(self, *args):
        action = FakeAction(str(args[-1]))
        self._actions.append(action)
        return FakeMenu()

    def addSeparator(self):
        self._actions.append(FakeAction(separator=True))

    def actions(self):
        return self._actions

    def exec(self, *_args):
        self.instances.append(self)


def test_similar_image_context_menu_starts_with_view(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")
    main_window = FakeMainWindow()
    monkeypatch.setattr(
        similar_dialog_module.SimilarImagesDialog, "start_search",
        lambda _self: None)
    monkeypatch.setattr(similar_dialog_module, "QMenu", FakeMenu)
    FakeMenu.instances.clear()

    dialog = similar_dialog_module.SimilarImagesDialog(
        str(image_path), main_window)
    dialog.preview_pane.controller.get_current_path = lambda: str(image_path)
    dialog._show_pane_context_menu(dialog.preview_pane.rect().center())

    actions = FakeMenu.instances[0].actions()
    assert actions[0].text() == UITexts.CONTEXT_MENU_VIEW
    assert actions[1].isSeparator()
    actions[0].trigger()
    main_window.open_viewer_for_path.assert_called_once_with(str(image_path))

    dialog.preview_pane.cleanup()
    dialog.close()
    dialog.deleteLater()
    main_window.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
