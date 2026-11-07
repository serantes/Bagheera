from types import SimpleNamespace

from PySide6.QtCore import QRect
from PySide6.QtGui import QStandardItem, QStandardItemModel

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
