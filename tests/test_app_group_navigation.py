from types import SimpleNamespace

import pytest

from PySide6.QtCore import (
    QItemSelectionModel, QPersistentModelIndex, QRect, QSortFilterProxyModel, Qt
)
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication

from bagheeraview.core import app as app_module
from bagheeraview.core import widgets
from bagheeraview.core.app import (
    MainWindow, ThumbnailDelegate, ThumbnailListView
)
from bagheeraview.core.constants import (
    DIR_ROLE, GROUP_NAME_ROLE, ITEM_TYPE_ROLE, MTIME_ROLE, PATH_ROLE,
    RATING_ROLE, TAGS_ROLE
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _window_with_groups():
    model = QStandardItemModel()
    for item_type in ("header", "thumbnail", "header", "thumbnail", "header"):
        item = QStandardItem()
        item.setData(item_type, ITEM_TYPE_ROLE)
        model.appendRow(item)
    return SimpleNamespace(
        proxy_model=model,
        _group_header_rows_cache=None,
    )


def test_group_header_neighbor_rows_follow_model_order():
    window = _window_with_groups()

    assert MainWindow._group_header_neighbor_row(window, 0, -1) is None
    assert MainWindow._group_header_neighbor_row(window, 0, 1) == 2
    assert MainWindow._group_header_neighbor_row(window, 2, -1) == 0
    assert MainWindow._group_header_neighbor_row(window, 2, 1) == 4
    assert MainWindow._group_header_neighbor_row(window, 4, 1) is None


def test_group_header_neighbor_row_rejects_non_header_rows():
    window = _window_with_groups()

    assert MainWindow._group_header_neighbor_row(window, 1, 1) is None


def test_header_controls_are_ordered_previous_next_then_collapse():
    buttons = ThumbnailDelegate.header_button_rects(QRect(0, 0, 500, 25))

    assert buttons["previous"].right() < buttons["next"].left()
    assert buttons["next"].right() < buttons["collapse"].left()
    assert ThumbnailDelegate.header_button_at(
        QRect(0, 0, 500, 25), buttons["previous"].center()) == "previous"


def test_selected_thumbnail_marks_its_group_active():
    model = QStandardItemModel()
    header = QStandardItem()
    header.setData("header", ITEM_TYPE_ROLE)
    header.setData("group-a", GROUP_NAME_ROLE)
    model.appendRow(header)
    thumbnail = QStandardItem()
    thumbnail.setData("thumbnail", ITEM_TYPE_ROLE)
    thumbnail.setData("/photos/a.jpg", PATH_ROLE)
    thumbnail.setData(10, MTIME_ROLE)
    thumbnail.setData(3, RATING_ROLE)
    model.appendRow(thumbnail)
    selected_index = model.index(1, 0)
    window = SimpleNamespace(
        thumbnail_view=SimpleNamespace(
            selectedIndexes=lambda: [selected_index]),
        proxy_model=model,
        _selected_group_names=set(),
        _get_group_info=lambda path, mtime, rating: ("key-a", "group-a"),
    )

    MainWindow._update_selected_group_names(window)

    assert window._selected_group_names == {"group-a"}


def test_expanding_group_scrolls_its_header_to_the_top():
    model = QStandardItemModel()
    header = QStandardItem()
    header.setData("header", ITEM_TYPE_ROLE)
    header.setData("group-a", GROUP_NAME_ROLE)
    model.appendRow(header)
    scrolled = []
    window = SimpleNamespace(
        proxy_model=SimpleNamespace(
            rowCount=model.rowCount,
            index=model.index,
            data=model.data,
            collapsed_groups=set(),
        ),
        thumbnail_view=SimpleNamespace(
            scrollTo=lambda index, hint: scrolled.append((index, hint))),
    )

    assert MainWindow._scroll_to_group(window, "group-a") is True
    assert scrolled[0][0].row() == 0
    assert scrolled[0][1].name == "PositionAtTop"


def test_expanding_collapsed_group_scrolls_after_filter_invalidation(monkeypatch):
    model = QStandardItemModel()
    header = QStandardItem()
    header.setData("header", ITEM_TYPE_ROLE)
    header.setData("group-a", GROUP_NAME_ROLE)
    model.appendRow(header)
    scrolled = []
    proxy = SimpleNamespace(
        collapsed_groups={"group-a"},
        invalidate=lambda: None,
        rowCount=model.rowCount,
        index=model.index,
        data=model.data,
    )
    window = SimpleNamespace(
        proxy_model=proxy,
        _group_header_rows_cache=None,
        _visible_paths_cache=[],
        _invalidate_group_header_rows=lambda: None,
        _schedule_section_scrubber_update=lambda: None,
        _scroll_to_group=lambda group_name: MainWindow._scroll_to_group(
            window, group_name),
        thumbnail_view=SimpleNamespace(
            scrollTo=lambda index, hint: scrolled.append((index, hint))),
    )
    monkeypatch.setattr(
        "bagheeraview.core.app.QTimer.singleShot",
        lambda delay, callback: callback())

    MainWindow.toggle_group_collapse(window, "group-a")

    assert proxy.collapsed_groups == set()
    assert scrolled[0][0].row() == 0
    assert scrolled[0][1].name == "PositionAtTop"


@pytest.mark.parametrize(
    ("command", "expected_paths"),
    [
        (QItemSelectionModel.Select,
         {"/photos/group-a/one.jpg", "/photos/group-a/two.jpg",
          "/photos/group-b/one.jpg"}),
        (QItemSelectionModel.Deselect, {"/photos/group-b/one.jpg"}),
        (QItemSelectionModel.Toggle,
         {"/photos/group-a/two.jpg", "/photos/group-b/one.jpg"}),
    ],
)
def test_group_selection_commands_affect_only_target_group(
        command, expected_paths):
    model = QStandardItemModel()
    for path in (
            "/photos/group-a/one.jpg",
            "/photos/group-a/two.jpg",
            "/photos/group-b/one.jpg"):
        item = QStandardItem()
        item.setData("thumbnail", ITEM_TYPE_ROLE)
        item.setData(path, PATH_ROLE)
        item.setData(10, MTIME_ROLE)
        item.setData(1, RATING_ROLE)
        model.appendRow(item)

    selection_model = QItemSelectionModel(model)
    selection_model.select(model.index(0, 0), QItemSelectionModel.Select)
    selection_model.select(model.index(2, 0), QItemSelectionModel.Select)
    window = SimpleNamespace(
        proxy_model=model,
        thumbnail_view=SimpleNamespace(
            isVisible=lambda: True,
            selectionModel=lambda: selection_model),
        _get_group_info=lambda path, mtime, rating: (
            None, path.rsplit("/", 2)[1]),
    )

    MainWindow._select_group_thumbnails(
        window, "group-a", command)

    selected_paths = {
        model.data(index, PATH_ROLE)
        for index in selection_model.selectedIndexes()
    }
    assert selected_paths == expected_paths


def test_right_clicking_group_header_preserves_thumbnail_selection(qapp):
    model = QStandardItemModel()
    for item_type in ("thumbnail", "thumbnail", "header"):
        item = QStandardItem()
        item.setData(item_type, ITEM_TYPE_ROLE)
        if item_type == "header":
            item.setFlags(Qt.ItemIsEnabled)
        model.appendRow(item)

    view = ThumbnailListView()
    view.setModel(model)
    view.setSelectionMode(QAbstractItemView.ExtendedSelection)
    view.setContextMenuPolicy(Qt.CustomContextMenu)
    view.resize(300, 200)
    view.show()
    qapp.processEvents()

    selection_model = view.selectionModel()
    selection_model.select(model.index(0, 0), QItemSelectionModel.Select)
    selection_model.select(model.index(1, 0), QItemSelectionModel.Select)

    header_rect = view.visualRect(model.index(2, 0))
    QTest.mouseClick(
        view.viewport(), Qt.RightButton, pos=header_rect.center())
    qapp.processEvents()

    assert [index.row() for index in selection_model.selectedIndexes()] == [0, 1]


@pytest.mark.parametrize("filtered", [False, True])
def test_restore_selection_keeps_all_visible_thumbnails(qapp, filtered):
    model = QStandardItemModel()
    paths = ["/photos/a.jpg", "/photos/b.jpg", "/photos/c.jpg"]
    indexes = {}
    for path in paths:
        item = QStandardItem(path)
        item.setData("thumbnail", ITEM_TYPE_ROLE)
        item.setData(path, PATH_ROLE)
        model.appendRow(item)
        indexes[path] = QPersistentModelIndex(item.index())

    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    if filtered:
        proxy.setFilterRegularExpression(r"[ab]\.jpg$")
    view = ThumbnailListView()
    view.setModel(proxy)
    view.setSelectionMode(QAbstractItemView.ExtendedSelection)
    window = SimpleNamespace(
        thumbnail_view=view,
        proxy_model=proxy,
        _path_to_model_index=indexes,
    )

    MainWindow.restore_selection(window, paths)

    expected = paths[:2] if filtered else paths
    assert {index.data(PATH_ROLE) for index in view.selectedIndexes()} == set(expected)
    assert view.currentIndex().data(PATH_ROLE) == paths[0]


def test_metadata_edits_preserve_selection_after_filter_refresh(
        qapp, tmp_path, monkeypatch):
    paths = [str(tmp_path / name) for name in ("a.jpg", "b.jpg", "c.jpg")]
    model = QStandardItemModel()
    indexes = {}
    for path in paths:
        item = QStandardItem(path)
        item.setData("thumbnail", ITEM_TYPE_ROLE)
        item.setData(path, PATH_ROLE)
        item.setData([], TAGS_ROLE)
        model.appendRow(item)
        indexes[path] = QPersistentModelIndex(item.index())

    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.prepare_filter = lambda: None
    proxy.add_to_cache = lambda path, tags: None
    view = ThumbnailListView()
    view.setModel(proxy)
    view.setSelectionMode(QAbstractItemView.ExtendedSelection)
    selection = view.selectionModel()
    for row in (0, 1):
        selection.select(proxy.index(row, 0), QItemSelectionModel.Select)

    window = SimpleNamespace(
        thumbnail_view=view,
        thumbnail_model=model,
        proxy_model=proxy,
        _path_to_model_index=indexes,
        tags_list=SimpleNamespace(rowCount=lambda: 0),
        filter_mode_group=SimpleNamespace(
            buttons=lambda: [SimpleNamespace(isChecked=lambda: True)]),
        filter_name_input=SimpleNamespace(text=lambda: ""),
        _extension_checkboxes={},
        is_cleaning=False,
        _suppress_updates=False,
        _visible_paths_cache=None,
        cache=SimpleNamespace(set_metadata=lambda *args: None),
        _update_internal_data=lambda *args, **kwargs: None,
        update_tag_list=lambda: None,
        get_visible_image_paths=lambda: paths,
        get_all_image_paths=lambda: paths,
        filter_stats_lbl=SimpleNamespace(setText=lambda text: None),
        filtered_count_lbl=SimpleNamespace(setText=lambda text: None),
        update_viewers_filter=lambda visible_paths: None,
    )
    window.get_selected_paths = lambda: MainWindow.get_selected_paths(window)
    window.restore_selection = lambda selected: MainWindow.restore_selection(
        window, selected)
    window.apply_filters = lambda: MainWindow.apply_filters(window)

    MainWindow.on_tags_edited(window, {path: ["new-tag"] for path in paths[:2]})

    assert set(window.get_selected_paths()) == set(paths[:2])
    assert [model.item(row).data(TAGS_ROLE) for row in range(3)] == [
        ["new-tag"], ["new-tag"], []]

    attributes = {}
    monkeypatch.setattr(
        widgets.XattrManager, "get_attribute",
        lambda path, name, default="": attributes.get((path, name), default))
    monkeypatch.setattr(
        widgets.XattrManager, "set_attribute",
        lambda path, name, value: attributes.__setitem__((path, name), value))
    monkeypatch.setattr(
        app_module.os, "getxattr",
        lambda path, name: attributes[(path, name)].encode())

    rating = widgets.RatingWidget()
    rating.set_files(window.get_selected_paths())
    rating.on_star_clicked(2)
    rating.rating_updated.connect(lambda: MainWindow.on_rating_edited(window))
    rating.save_rating()
    window.apply_filters()

    assert set(window.get_selected_paths()) == set(paths[:2])
    assert [model.item(row).data(RATING_ROLE) for row in range(3)] == [4, 4, None]
    assert set(rating.file_paths) == set(paths[:2])

    comment = widgets.CommentWidget()
    comment.set_files(window.get_selected_paths())
    comment.comment_edit.setPlainText("comment")
    comment.save_comment()
    window.apply_filters()

    assert set(window.get_selected_paths()) == set(paths[:2])
    assert {
        path for path in paths
        if attributes.get((path, widgets.XATTR_COMMENT_NAME)) == "comment"
    } == set(paths[:2])


def test_scrubber_sections_use_visible_group_headers_and_thumbnails():
    model = QStandardItemModel()
    model.setColumnCount(1)
    for item_type, group, label in (
            ("header", "/photos/group-a", "Group A"),
            ("thumbnail", "/photos/group-a", None),
            ("header", "/photos/group-b", "Group B")):
        item = QStandardItem()
        item.setData(item_type, ITEM_TYPE_ROLE)
        if item_type == "header":
            item.setData(group, GROUP_NAME_ROLE)
            item.setData(f"{label} - 12 images", DIR_ROLE)
        else:
            item.setData(f"{group}/a.jpg", PATH_ROLE)
            item.setData(10, MTIME_ROLE)
            item.setData(1, RATING_ROLE)
        model.appendRow(item)

    class Scrubber:
        sections = None
        tooltips = None
        visible = False

        def set_sections(self, sections, tooltips=None):
            self.sections = sections
            self.tooltips = tooltips

        def setVisible(self, visible):
            self.visible = visible

    window = SimpleNamespace(
        proxy_model=SimpleNamespace(
            group_by_folder=True,
            group_by_day=False,
            group_by_week=False,
            group_by_month=False,
            group_by_year=False,
            group_by_rating=False,
            rowCount=model.rowCount,
            index=model.index,
            data=model.data,
        ),
        _is_grouped_view=lambda: True,
        _timeline_group_label=lambda group_name: group_name.rsplit("/", 1)[-1],
        _get_group_info=lambda path, mtime, rating: (
            path.rsplit("/", 1)[0], path.rsplit("/", 1)[0]),
        thumbnail_scrubber=Scrubber(),
    )

    MainWindow._update_section_scrubber(window)

    assert window.thumbnail_scrubber.sections == [
        ("group-a", 0, 2),
        ("group-b", 2, 1),
    ]
    assert window.thumbnail_scrubber.tooltips == [
        "Group A - 12 images",
        "Group B - 12 images",
    ]
    assert window.thumbnail_scrubber.visible is True


@pytest.mark.parametrize(
    ("config", "expected_visible"),
    [
        ({}, True),
        ({"thumbnails_timeline_enabled": False}, False),
    ],
)
def test_timeline_visibility_respects_setting(config, expected_visible, monkeypatch):
    class Scrubber:
        visible = None
        sections = None

        def setVisible(self, visible):
            self.visible = visible

        def set_sections(self, sections):
            self.sections = sections

    window = SimpleNamespace(
        _is_grouped_view=lambda: True,
        thumbnail_scrubber=Scrubber(),
        _update_section_scrubber=lambda: None,
    )
    monkeypatch.setattr(app_module, "APP_CONFIG", config)

    MainWindow._update_section_scrubber_visibility(window)

    assert window.thumbnail_scrubber.visible is expected_visible
    if not expected_visible:
        assert window.thumbnail_scrubber.sections == []


@pytest.mark.parametrize(
    ("grouping", "group_name", "expected_label"),
    [
        ("group_by_folder", "/a/b/c", "c"),
        ("group_by_day", "2024-05-09", "09 05"),
        ("group_by_week", "2024 - Semana 07", "07 2024"),
        ("group_by_month", "May 2024", "05 2024"),
        ("group_by_year", "2024", "2024"),
        ("group_by_rating", "3 Stars", "3"),
    ],
)
def test_timeline_group_labels_match_grouping_mode(
        grouping, group_name, expected_label, monkeypatch):
    if grouping == "group_by_month":
        monkeypatch.setattr(
            app_module, "UITexts",
            SimpleNamespace(MONTH_NAMES=(
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November",
                "December",
            )),
        )
    flags = {
        "group_by_folder": False,
        "group_by_day": False,
        "group_by_week": False,
        "group_by_month": False,
        "group_by_year": False,
        "group_by_rating": False,
    }
    flags[grouping] = True
    window = SimpleNamespace(proxy_model=SimpleNamespace(**flags))

    assert MainWindow._timeline_group_label(window, group_name) == expected_label
