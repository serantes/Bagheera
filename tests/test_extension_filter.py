from types import SimpleNamespace

import pytest
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication, QGroupBox, QScrollArea, QVBoxLayout, QWidget,
)

from bagheeraview.core.app import MainWindow, ThumbnailSortFilterProxyModel
from bagheeraview.core.constants import ITEM_TYPE_ROLE, PATH_ROLE


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_extension_filter_list_adds_checked_boxes_for_discovered_extensions(
        app):
    widget = QWidget()
    group = QGroupBox(widget)
    scroll = QScrollArea(group)
    extension_filter = SimpleNamespace(
        extension_filter_layout=QVBoxLayout(widget),
        extension_filter_widget=widget,
        extension_filter_group=group,
        extension_filter_scroll=scroll,
        _extension_checkboxes={},
        found_items_data=[],
        apply_filters=lambda: None,
        _resize_extension_filter_list=lambda: (
            MainWindow._resize_extension_filter_list(extension_filter)),
    )

    MainWindow._update_extension_filter_list(
        extension_filter,
        ["/photos/first.JPG", "/photos/second.png", "/photos/no-extension"],
    )

    assert set(extension_filter._extension_checkboxes) == {
        ".jpg", ".png", ""}
    assert all(box.isChecked()
               for box in extension_filter._extension_checkboxes.values())
    assert scroll.height() == sum(
        checkbox.sizeHint().height()
        for checkbox in list(extension_filter._extension_checkboxes.values())[:2]
    )
    assert not group.isHidden()


def test_extension_filter_area_fits_single_checkbox(app):
    widget = QWidget()
    group = QGroupBox(widget)
    scroll = QScrollArea(group)
    checkbox_widget = QWidget()
    extension_filter = SimpleNamespace(
        extension_filter_layout=QVBoxLayout(checkbox_widget),
        extension_filter_widget=checkbox_widget,
        extension_filter_group=group,
        extension_filter_scroll=scroll,
        _extension_checkboxes={},
        found_items_data=[],
        apply_filters=lambda: None,
        _resize_extension_filter_list=lambda: (
            MainWindow._resize_extension_filter_list(extension_filter)),
    )

    MainWindow._update_extension_filter_list(
        extension_filter, ["/photos/only.jpg"])

    checkbox = extension_filter._extension_checkboxes[".jpg"]
    assert scroll.height() == checkbox.sizeHint().height()


def test_extension_filter_combines_with_filename_and_tag_filters(app):
    proxy = ThumbnailSortFilterProxyModel()
    proxy.main_win = SimpleNamespace()
    source = QStandardItemModel()
    files = [
        ("/photos/sample-alpha.jpg", {"cat"}),
        ("/photos/sample-alpha.png", {"cat"}),
        ("/photos/other-beta.jpg", {"cat"}),
        ("/photos/sample-alpha.gif", {"dog"}),
    ]

    for path, tags in files:
        item = QStandardItem()
        item.setData(path, PATH_ROLE)
        item.setData("thumbnail", ITEM_TYPE_ROLE)
        source.appendRow(item)
        proxy.add_to_cache(path, tags)

    proxy.setSourceModel(source)
    proxy.name_filter = "sample"
    proxy.include_tags = {"cat"}
    proxy.excluded_extensions = {".png", ".gif"}
    proxy.prepare_filter()
    proxy.invalidate()

    visible_paths = {
        proxy.index(row, 0).data(PATH_ROLE)
        for row in range(proxy.rowCount())
    }
    assert visible_paths == {"/photos/sample-alpha.jpg"}


def test_extension_filter_can_exclude_extensionless_files(app):
    proxy = ThumbnailSortFilterProxyModel()
    source = QStandardItemModel()
    for path in ("/photos/image.jpg", "/photos/image"):
        item = QStandardItem()
        item.setData(path, PATH_ROLE)
        item.setData("thumbnail", ITEM_TYPE_ROLE)
        source.appendRow(item)

    proxy.setSourceModel(source)
    proxy.excluded_extensions = {""}
    proxy.invalidate()

    assert proxy.rowCount() == 1
    assert proxy.index(0, 0).data(PATH_ROLE) == "/photos/image.jpg"


def test_extension_filter_is_applied_to_visible_image_paths():
    window = SimpleNamespace(
        _visible_paths_cache=None,
        found_items_data=[
            ("/photos/keep.jpg", None, 1, [], 0, None, None),
            ("/photos/hide.png", None, 1, [], 0, None, None),
        ],
        proxy_model=SimpleNamespace(
            name_filter="",
            include_tags=set(),
            exclude_tags=set(),
            match_mode="AND",
            excluded_extensions={".png"},
            collapsed_groups=set(),
            group_by_folder=False,
            group_by_day=False,
            group_by_week=False,
            group_by_month=False,
            group_by_year=False,
            group_by_rating=False,
        ),
    )

    assert MainWindow.get_visible_image_paths(window) == ["/photos/keep.jpg"]
