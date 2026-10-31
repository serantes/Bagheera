from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication

from bagheeraview.core.app import MainWindow, ThumbnailSortFilterProxyModel
from bagheeraview.core.constants import (
    APP_CONFIG, ITEM_TYPE_ROLE, MTIME_ROLE, PATH_ROLE,
)
from bagheeraview.core.imagescanner import ImageScanner


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _append_item(model, item_type, path, name, mtime=0):
    item = QStandardItem(name)
    item.setData(item_type, ITEM_TYPE_ROLE)
    item.setData(path, PATH_ROLE)
    item.setData(mtime, MTIME_ROLE)
    model.appendRow(item)


def test_navigation_scanner_lists_immediate_directories_and_respects_hidden(
        tmp_path, monkeypatch):
    visible = tmp_path / "visible"
    hidden = tmp_path / ".hidden"
    visible.mkdir()
    hidden.mkdir()
    (tmp_path / "image.jpg").touch()
    (tmp_path / "document.txt").touch()
    (visible / "nested.jpg").touch()
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_dirs", False)
    monkeypatch.delitem(APP_CONFIG, "show_hidden_dirs", raising=False)

    scanner = ImageScanner(None, [str(tmp_path)], directory_navigation=True)
    results = []
    scanner.directories_found.connect(
        lambda root, paths: results.append((root, paths)))

    scanner._scan_navigation_directory()

    assert results == [(str(tmp_path), [str(visible)])]
    assert scanner.all_files == [str(tmp_path / "image.jpg")]


def test_navigation_scanner_honors_show_hidden_dirs_alias(
        tmp_path, monkeypatch):
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_dirs", False)
    monkeypatch.setitem(APP_CONFIG, "show_hidden_dirs", True)

    scanner = ImageScanner(None, [str(tmp_path)], directory_navigation=True)
    results = []
    scanner.directories_found.connect(
        lambda root, paths: results.append(paths))

    scanner._scan_navigation_directory()

    assert results == [[str(hidden)]]


def test_directories_ignore_filters_in_flat_and_are_hidden_when_grouped(app):
    source = QStandardItemModel()
    _append_item(source, "parent_directory", "/photos", "..")
    _append_item(source, "directory", "/photos/child", "child")
    _append_item(source, "thumbnail", "/photos/image.jpg", "image.jpg")

    proxy = ThumbnailSortFilterProxyModel()
    proxy.main_win = SimpleNamespace()
    proxy.setSourceModel(source)
    proxy.name_filter = "no-match"
    proxy._name_filter_active = True
    proxy.excluded_extensions = {".jpg"}
    proxy.include_tags = {"missing"}
    proxy._tag_filter_active = True

    proxy.invalidate()
    assert [proxy.index(row, 0).data(ITEM_TYPE_ROLE)
            for row in range(proxy.rowCount())] == [
                "parent_directory", "directory"]

    proxy.group_by_folder = True
    proxy.invalidate()
    assert proxy.rowCount() == 0


@pytest.mark.parametrize(
    ("sort_order", "expected_directories"),
    [
        (Qt.AscendingOrder, ["/photos/a", "/photos/z"]),
        (Qt.DescendingOrder, ["/photos/z", "/photos/a"]),
    ],
)
def test_navigation_rows_keep_parent_and_directories_before_images(
        app, sort_order, expected_directories):
    source = QStandardItemModel()
    _append_item(source, "thumbnail", "/photos/image.jpg", "image.jpg", 5)
    _append_item(source, "directory", "/photos/z", "z", 20)
    _append_item(source, "parent_directory", "/", "..", 0)
    _append_item(source, "directory", "/photos/a", "a", 10)

    proxy = ThumbnailSortFilterProxyModel()
    proxy.setSourceModel(source)
    proxy.setSortRole(MTIME_ROLE)
    proxy.sort(0, sort_order)

    rows = [proxy.index(row, 0) for row in range(proxy.rowCount())]
    assert [index.data(ITEM_TYPE_ROLE) for index in rows] == [
        "parent_directory", "directory", "directory", "thumbnail"]
    assert [index.data(PATH_ROLE) for index in rows[1:3]] == \
        expected_directories


@pytest.mark.parametrize(
    ("sort_order", "expected_directories"),
    [
        (Qt.AscendingOrder, ["/photos/a", "/photos/z"]),
        (Qt.DescendingOrder, ["/photos/z", "/photos/a"]),
    ],
)
def test_name_sorting_keeps_navigation_rows_before_images(
        app, sort_order, expected_directories):
    source = QStandardItemModel()
    _append_item(source, "thumbnail", "/photos/image.jpg", "0-image.jpg")
    _append_item(source, "directory", "/photos/z", "z")
    _append_item(source, "parent_directory", "/", "..")
    _append_item(source, "directory", "/photos/a", "a")

    proxy = ThumbnailSortFilterProxyModel()
    proxy.setSourceModel(source)
    proxy.sort(0, sort_order)

    rows = [proxy.index(row, 0) for row in range(proxy.rowCount())]
    assert [index.data(ITEM_TYPE_ROLE) for index in rows] == [
        "parent_directory", "directory", "directory", "thumbnail"]
    assert [index.data(PATH_ROLE) for index in rows[1:3]] == \
        expected_directories


def test_navigation_items_add_parent_even_without_children(tmp_path, app):
    window = SimpleNamespace(
        thumbnail_model=QStandardItemModel(),
        _directory_navigation_root=str(tmp_path),
        _directory_navigation_paths=[],
    )

    MainWindow._insert_navigation_items(window)

    assert window.thumbnail_model.rowCount() == 1
    parent = window.thumbnail_model.item(0)
    assert parent.data(ITEM_TYPE_ROLE) == "parent_directory"
    assert parent.data(PATH_ROLE) == str(tmp_path.parent)


def test_navigation_items_omit_parent_at_filesystem_root(app):
    window = SimpleNamespace(
        thumbnail_model=QStandardItemModel(),
        _directory_navigation_root="/",
        _directory_navigation_paths=[],
    )

    MainWindow._insert_navigation_items(window)

    assert window.thumbnail_model.rowCount() == 0


def test_selected_paths_ignore_directory_rows(app):
    source = QStandardItemModel()
    _append_item(source, "directory", "/photos/child", "child")
    _append_item(source, "thumbnail", "/photos/image.jpg", "image.jpg")
    indexes = [source.index(row, 0) for row in range(source.rowCount())]
    window = SimpleNamespace(
        thumbnail_view=SimpleNamespace(selectedIndexes=lambda: indexes),
        proxy_model=source,
    )

    assert MainWindow.get_selected_paths(window) == ["/photos/image.jpg"]
