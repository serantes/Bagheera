from types import SimpleNamespace
from datetime import datetime

import pytest

from bagheeraview.core import app as app_module
from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import UITexts, _UI_TEXTS


@pytest.mark.parametrize(
    "group_field",
    ["group_by_day", "group_by_week", "group_by_month", "group_by_year"],
)
def test_date_groups_follow_ascending_date_sort(group_field):
    group_flags = {
        "group_by_folder": False,
        "group_by_day": False,
        "group_by_week": False,
        "group_by_month": False,
        "group_by_year": False,
        "group_by_rating": False,
    }
    group_flags[group_field] = True
    window = SimpleNamespace(
        proxy_model=SimpleNamespace(**group_flags),
        sort_combo=SimpleNamespace(currentText=lambda: UITexts.SORT_DATE_ASC),
    )

    assert MainWindow._is_reverse_group_order(window) is False


@pytest.mark.parametrize(
    "sort_order",
    [UITexts.SORT_DATE_DESC, UITexts.SORT_NAME_ASC, UITexts.SORT_NAME_DESC],
)
def test_date_groups_remain_descending_for_other_sort_orders(sort_order):
    window = SimpleNamespace(
        proxy_model=SimpleNamespace(
            group_by_folder=False,
            group_by_day=True,
            group_by_week=False,
            group_by_month=False,
            group_by_year=False,
            group_by_rating=False,
        ),
        sort_combo=SimpleNamespace(currentText=lambda: sort_order),
    )

    assert MainWindow._is_reverse_group_order(window) is True


def test_folder_groups_keep_their_existing_ascending_order():
    window = SimpleNamespace(
        proxy_model=SimpleNamespace(
            group_by_folder=True,
            group_by_day=False,
            group_by_week=False,
            group_by_month=False,
            group_by_year=False,
            group_by_rating=False,
        ),
        sort_combo=SimpleNamespace(currentText=lambda: UITexts.SORT_DATE_ASC),
    )

    assert MainWindow._is_reverse_group_order(window) is False


def test_date_group_sort_key_uses_full_timestamp_then_name():
    earlier = ("/photos/z-earlier.jpg", None, 1_700_000_000.0, [], 0, 1, 1)
    later = ("/photos/a-later.jpg", None, 1_700_000_360.0, [], 0, 2, 1)
    tied_by_time = ("/photos/a-earlier.jpg", None, 1_700_000_000.0, [], 0, 3, 1)

    sorted_items = sorted(
        [earlier, later, tied_by_time],
        key=MainWindow._date_group_sort_key,
    )

    assert [item[0] for item in sorted_items] == [
        "/photos/a-earlier.jpg",
        "/photos/z-earlier.jpg",
        "/photos/a-later.jpg",
    ]


@pytest.mark.parametrize(
    ("language", "expected_name"),
    [
        ("en", "May"),
        ("es", "Mayo"),
        ("gl", "Maio"),
    ],
)
def test_month_groups_use_selected_language(
        monkeypatch, language, expected_name):
    timestamp = datetime(2024, 5, 15).timestamp()
    proxy_model = SimpleNamespace(
        group_by_folder=False,
        group_by_rating=False,
        group_by_day=False,
        group_by_week=False,
        group_by_month=True,
        group_by_year=False,
    )
    window = SimpleNamespace(
        proxy_model=proxy_model,
        _group_info_cache={},
    )
    monkeypatch.setattr(
        app_module,
        "UITexts",
        SimpleNamespace(
            MONTH_NAMES=_UI_TEXTS[language]["MONTH_NAMES"],
        ),
    )

    _, label = MainWindow._get_group_info(
        window, "/photos/image.jpg", timestamp, 0)

    assert label == f"{expected_name} 2024"
    assert len(_UI_TEXTS[language]["MONTH_NAMES"]) == 12
