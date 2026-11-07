from types import SimpleNamespace

import pytest

from PySide6.QtCore import QRect
from PySide6.QtGui import QStandardItem, QStandardItemModel

from bagheeraview.core import app as app_module
from bagheeraview.core.app import MainWindow, ThumbnailDelegate
from bagheeraview.core.constants import (
    DIR_ROLE, GROUP_NAME_ROLE, ITEM_TYPE_ROLE, MTIME_ROLE, PATH_ROLE, RATING_ROLE
)


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
