import pytest
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QApplication

from bagheeraview.core import widgets


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def create_tag_widget():
    tag_widget = widgets.TagEditWidget()
    tag_widget.source_model.clear()
    tag_widget.item_mapping = {}
    tag_widget.root_favs = QStandardItem("Used Tags")
    tag_widget.root_all = QStandardItem("All Tags")
    tag_widget.source_model.appendRow(tag_widget.root_favs)
    tag_widget.source_model.appendRow(tag_widget.root_all)
    return tag_widget


def test_tag_with_information_file_is_underlined_in_tree(qapp, tmp_path,
                                                          monkeypatch):
    monkeypatch.setattr(widgets, "DIRECTORY_TAG_INFO", str(tmp_path))
    (tmp_path / "animals_cat.md").write_text("Notes", encoding="utf-8")
    tag_widget = create_tag_widget()

    tag_widget.get_or_create_node("animals/cat", tag_widget.root_all, True, False)
    tag_widget.get_or_create_node("animals/cat", tag_widget.root_favs, True, False)

    assert tag_widget.item_mapping["animals/cat"][0].font().underline()
    assert tag_widget.item_mapping["animals/cat"][1].font().underline()
    assert not tag_widget.root_all.child(0).font().underline()


def test_double_click_opens_existing_tag_information(qapp, tmp_path,
                                                       monkeypatch):
    monkeypatch.setattr(widgets, "DIRECTORY_TAG_INFO", str(tmp_path))
    info_path = tmp_path / "animals_cat.md"
    info_path.write_text("Notes", encoding="utf-8")
    tag_widget = create_tag_widget()
    tag_widget.main_win = object()
    tag_widget.get_or_create_node("animals/cat", tag_widget.root_all, True, False)
    source_index = tag_widget.item_mapping["animals/cat"][0].index()
    proxy_index = tag_widget.proxy_model.mapFromSource(source_index)
    opened = []
    monkeypatch.setattr(
        tag_widget, "on_tag_info_requested",
        lambda index: opened.append(index))

    tag_widget.on_tag_info_double_clicked(proxy_index)

    assert opened == [proxy_index]


def test_double_click_without_tag_information_does_nothing(qapp, tmp_path,
                                                             monkeypatch):
    monkeypatch.setattr(widgets, "DIRECTORY_TAG_INFO", str(tmp_path))
    tag_widget = create_tag_widget()
    tag_widget.get_or_create_node("animals/cat", tag_widget.root_all, True, False)
    source_index = tag_widget.item_mapping["animals/cat"][0].index()
    proxy_index = tag_widget.proxy_model.mapFromSource(source_index)
    opened = []
    monkeypatch.setattr(
        tag_widget, "on_tag_info_requested",
        lambda index: opened.append(index))

    tag_widget.on_tag_info_double_clicked(proxy_index)

    assert opened == []


def test_add_tag_uses_selected_tag_as_prefix_and_places_cursor_at_end(
        qapp, monkeypatch):
    tag_widget = create_tag_widget()
    tag_widget.get_or_create_node(
        "Travel/Camboxa", tag_widget.root_all, True, False)
    tag_widget.get_or_create_node(
        "Travel/Camboxa", tag_widget.root_favs, True, False)
    selected_index = tag_widget.item_mapping["Travel/Camboxa"][0].index()
    tag_widget.tree_view.setCurrentIndex(
        tag_widget.proxy_model.mapFromSource(selected_index))
    dialog_state = {}

    class FakeInputDialog:
        def __init__(self, parent):
            pass

        def setWindowTitle(self, title):
            pass

        def setLabelText(self, label):
            pass

        def setInputMode(self, input_mode):
            pass

        def setTextValue(self, value):
            dialog_state["value"] = value

        def findChild(self, child_type):
            assert child_type is widgets.QLineEdit
            return self

        def setCursorPosition(self, position):
            dialog_state["cursor_position"] = position

        def exec(self):
            return widgets.QDialog.DialogCode.Accepted

        def textValue(self):
            return "Travel/Camboxa/NewTrip"

    FakeInputDialog.TextInput = 0
    monkeypatch.setattr(widgets, "QInputDialog", FakeInputDialog)

    tag_widget.create_new_tag()

    assert dialog_state == {
        "value": "Travel/Camboxa/",
        "cursor_position": len("Travel/Camboxa/"),
    }
    assert "Travel/Camboxa/NewTrip" in tag_widget.manually_changed
