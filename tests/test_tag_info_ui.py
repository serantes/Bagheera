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
