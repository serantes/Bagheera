import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import app as app_module
from bagheeraview.core.widgets import LayoutSelectionDialog, LayoutsWidget


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _layout_file(directory, name, created_at, last_used_at):
    path = directory / f"{name}.layout"
    path.write_text(json.dumps({
        "created_at": created_at,
        "last_used_at": last_used_at,
    }), encoding="utf-8")
    return str(path)


def _displayed_names(dialog):
    return [
        dialog.table.item(row, 0).text()
        for row in range(dialog.table.rowCount())
    ]


def test_layout_selection_sorts_by_last_use_by_default(qapp, tmp_path):
    older = _layout_file(tmp_path, "Older", 10, 20)
    newer = _layout_file(tmp_path, "Newer", 30, 40)

    dialog = LayoutSelectionDialog([older, newer])

    assert _displayed_names(dialog) == ["Newer", "Older"]
    assert dialog.selected_path() == newer


def test_layout_selection_supports_name_and_creation_date_order(qapp,
                                                                tmp_path):
    zulu = _layout_file(tmp_path, "Zulu", 40, 40)
    alpha = _layout_file(tmp_path, "alpha", 10, 10)
    middle = _layout_file(tmp_path, "Middle", 30, 30)

    dialog = LayoutSelectionDialog([zulu, alpha, middle])
    dialog.sort_field_combo.setCurrentIndex(
        dialog.sort_field_combo.findData("name"))
    dialog.sort_order_combo.setCurrentIndex(
        dialog.sort_order_combo.findData("ascending"))
    assert _displayed_names(dialog) == ["alpha", "Middle", "Zulu"]

    dialog.sort_field_combo.setCurrentIndex(
        dialog.sort_field_combo.findData("created_at"))
    dialog.sort_order_combo.setCurrentIndex(
        dialog.sort_order_combo.findData("descending"))
    assert _displayed_names(dialog) == ["Zulu", "Middle", "alpha"]


def test_layout_selection_supports_ascending_last_use(qapp, tmp_path):
    older = _layout_file(tmp_path, "Older", 10, 20)
    newer = _layout_file(tmp_path, "Newer", 30, 40)

    dialog = LayoutSelectionDialog([older, newer])
    dialog.sort_order_combo.setCurrentIndex(
        dialog.sort_order_combo.findData("ascending"))

    assert _displayed_names(dialog) == ["Older", "Newer"]


def test_save_layout_starts_empty_offers_existing_names_and_rejects_empty(
        tmp_path, monkeypatch):
    (tmp_path / "Existing.layout").write_text("{}", encoding="utf-8")
    (tmp_path / "Another.layout").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(app_module, "LAYOUTS_DIR", str(tmp_path))
    prompts = []
    responses = iter([("", True), ("", False)])

    def get_item(_parent, _title, _label, items, current, editable):
        prompts.append((items, current, editable))
        return next(responses)

    warnings = []
    monkeypatch.setattr(app_module.QInputDialog, "getItem", get_item)
    monkeypatch.setattr(
        app_module.QMessageBox, "warning",
        lambda *args: warnings.append(args))

    app_module.MainWindow.save_layout(SimpleNamespace(is_xcb=True))

    assert prompts == [
        (["", "Another", "Existing"], 0, True),
        (["", "Another", "Existing"], 0, True),
    ]
    assert len(warnings) == 1
    assert warnings[0][2] == app_module.UITexts.LAYOUT_NAME_REQUIRED


def test_layouts_save_button_opens_name_selector(qapp):
    calls = []

    class MainWindow:
        def save_layout(self, **kwargs):
            calls.append(kwargs)

    layouts_widget = LayoutsWidget(MainWindow())
    layouts_widget.save_selected_layout()

    assert calls == [{}]
