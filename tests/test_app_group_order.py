from types import SimpleNamespace

import pytest

from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import UITexts


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
