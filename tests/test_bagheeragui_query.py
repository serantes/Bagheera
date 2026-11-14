import pytest
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QHeaderView, QToolButton

from bagheeragui.gui import app as gui


@pytest.fixture
def window(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui, "load_app_config", lambda: {})
    monkeypatch.setattr(gui, "save_app_config", lambda config: None)
    window = gui.BagheeraSearchWindow()
    yield window
    window.close()
    app.processEvents()


class FakeSignal:
    def connect(self, callback):
        pass


@pytest.fixture
def searches(monkeypatch):
    calls = []

    class FakeWorker:
        def __init__(self, query, main_options, other_options, *args):
            calls.append((query, main_options, other_options))
            self.results_found = FakeSignal()
            self.search_failed = FakeSignal()
            self.finished = FakeSignal()

        def start(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr(gui, "SearchWorker", FakeWorker)
    return calls


def test_query_bar_and_advanced_fields_combine_using_new_syntax(window, searches):
    window.query_input.setEditText(
        'album HAVING tags="HAVING SUBQUERY" SUBQUERY cat '
        'HAVING rating=5 OR NOT SUBQUERY dog')
    window.having_input.setEditText("width > height")
    window.subquery_active_check.setChecked(True)
    window.subquery_input.setEditText("bird")
    window.subquery_having_input.setEditText("rating=7")
    window.subquery_operator_combo.setCurrentIndex(
        window.subquery_operator_combo.findData("OR EXCLUSIVE"))
    window.type_combo.setCurrentIndex(window.type_combo.findData("image"))
    window.offset_spin.setValue(2)
    window.limit_spin.setValue(5)

    window.perform_search()

    query, main, other = searches[0]
    assert query == "album"
    assert main["type"] == "image"
    assert "limit" not in main and "offset" not in main
    assert other["having"] == 'tags="HAVING SUBQUERY" AND width > height'
    assert other["subqueries"] == [
        ("AND", "cat", "rating=5"), ("OR NOT", "dog", None),
        ("OR EXCLUSIVE", "bird", "rating=7"),
    ]
    assert (other["limit"], other["offset"]) == (5, 2)
    assert other["subquery"] is None
    assert window.config["query_history"][0].startswith("album HAVING")


@pytest.mark.parametrize("text,active,expected", [
    ("album HAVING", False, []),
    ("album SUBQUERY HAVING", False, [("AND", "", None)]),
    ("album", True, [("AND", "", None)]),
])
def test_empty_clauses_and_empty_subqueries(window, searches, text, active, expected):
    window.query_input.setEditText(text)
    window.subquery_active_check.setChecked(active)
    window.perform_search()
    _, main, other = searches[0]
    assert other["having"] is None
    assert other.get("subqueries", []) == expected
    if not expected:
        assert main["limit"] == 100


def test_cli_options_are_rejected_but_quoted_literals_are_allowed(window, searches, monkeypatch):
    warnings = []
    monkeypatch.setattr(gui.QMessageBox, "warning",
                        lambda parent, title, message: warnings.append(message))
    window.query_input.setEditText("album SUBQUERY --type image")
    window.perform_search()
    assert not searches
    assert warnings and "--type" in warnings[0]

    window.query_input.setEditText('filename="--type image" SUBQUERY')
    window.perform_search()
    assert searches[0][0] == 'filename="--type image"'


def test_operator_state_is_restored_and_offset_resets_on_advanced_changes(window, searches):
    window.config["last_state"] = {
        "query": "album", "subquery_active": True, "subquery": "cat",
        "subquery_having": "rating=5", "subquery_operator": "AND NOT",
    }
    window._restore_state()
    assert window.subquery_operator_combo.currentData() == "AND NOT"
    assert window.subquery_operator_combo.isEnabled()
    assert window.subquery_input.currentText() == "cat"
    window.offset_spin.setValue(8)
    window.subquery_having_input.setEditText("rating=7")
    assert window.offset_spin.value() == 0
    window._save_current_state()
    assert window.config["last_state"]["subquery_operator"] == "AND NOT"
    window._clear_filters()
    assert window.subquery_operator_combo.currentData() == "AND"
    assert not window.subquery_operator_combo.isEnabled()


def test_dynamic_subqueries_keep_order_history_and_offset(window, searches):
    window.query_input.setEditText("album SUBQUERY from_bar")
    window.subquery_active_check.setChecked(True)
    window.subquery_input.setEditText("first")
    second = window._add_subquery_row()
    second.operator_combo.setCurrentIndex(second.operator_combo.findData("OR"))
    second.query_input.setEditText("second")
    third = window._add_subquery_row()
    third.operator_combo.setCurrentIndex(third.operator_combo.findData("AND NOT"))
    third.having_input.setEditText("rating=5")
    window.offset_spin.setValue(8)
    second.remove_button.click()
    assert window.offset_spin.value() == 0

    window.perform_search()

    assert searches[0][2]["subqueries"] == [
        ("AND", "from_bar", None), ("AND", "first", None),
        ("AND NOT", "", "rating=5"),
    ]
    assert window.config["subquery_history"] == ["first"]
    assert window.config["subquery_having_history"] == ["rating=5"]
    assert third.query_input.findText("first") >= 0
    assert window.subquery_having_input.findText("rating=5") >= 0


def test_dynamic_subqueries_restore_and_clear_without_losing_inactive_edits(window, searches):
    window.subquery_active_check.setChecked(True)
    window.subquery_input.setEditText("first")
    row = window._add_subquery_row()
    row.operator_combo.setCurrentIndex(row.operator_combo.findData("OR EXCLUSIVE"))
    row.query_input.setEditText("second")
    row.having_input.setEditText("rating=5")
    window.subquery_active_check.setChecked(False)
    window._save_current_state()

    window._restore_state()
    assert len(window.subquery_rows) == 2
    assert not window.subquery_active_check.isChecked()
    assert window.subquery_rows[1].query_input.currentText() == "second"
    assert window.subquery_rows[1].having_input.currentText() == "rating=5"
    assert window.subquery_rows[1].operator_combo.currentData() == "OR EXCLUSIVE"
    window.subquery_active_check.setChecked(True)
    window.perform_search()
    assert searches[0][2]["subqueries"] == [
        ("AND", "first", None), ("OR EXCLUSIVE", "second", "rating=5")]
    window._clear_filters()
    assert len(window.subquery_rows) == 1
    assert not window.subquery_active_check.isChecked()
    assert window.subquery_input.currentText() == ""


def test_dynamic_subqueries_restore_in_a_new_window(window, monkeypatch):
    window.subquery_active_check.setChecked(True)
    window.subquery_input.setEditText("first")
    row = window._add_subquery_row()
    row.query_input.setEditText("second")
    row.operator_combo.setCurrentIndex(row.operator_combo.findData("OR NOT"))
    row.having_input.setEditText("rating=5")
    window._save_current_state()
    saved_config = window.config.copy()
    monkeypatch.setattr(gui, "load_app_config", lambda: saved_config)

    restored = gui.BagheeraSearchWindow()
    try:
        assert restored.subquery_active_check.isChecked()
        assert restored.subquery_input.currentText() == "first"
        assert len(restored.subquery_rows) == 2
        assert restored.subquery_rows[1].operator_combo.currentData() == "OR NOT"
        assert restored.subquery_rows[1].query_input.currentText() == "second"
        assert restored.subquery_rows[1].having_input.currentText() == "rating=5"
    finally:
        restored.close()


def test_clearing_shared_history_preserves_other_row_edits(window, searches, monkeypatch):
    window.subquery_active_check.setChecked(True)
    window.subquery_input.setEditText("first")
    row = window._add_subquery_row()
    row.query_input.setEditText("second")
    window.perform_search()
    monkeypatch.setattr(gui.QMessageBox, "question",
                        lambda *args: gui.QMessageBox.Yes)

    window._clear_combo_history(window.subquery_input, "subquery_history")

    assert window.config["subquery_history"] == []
    assert window.subquery_input.currentText() == ""
    assert row.query_input.currentText() == "second"
    assert row.query_input.count() == 0


def test_invalid_option_in_extra_subquery_is_rejected(window, searches, monkeypatch):
    warnings = []
    monkeypatch.setattr(gui.QMessageBox, "warning",
                        lambda parent, title, message: warnings.append(message))
    window.subquery_active_check.setChecked(True)
    row = window._add_subquery_row()
    row.having_input.setEditText("--type image")
    window.perform_search()
    assert not searches
    assert warnings and "--type" in warnings[0]


def test_dynamic_subqueries_scroll_and_directory_has_space(window):
    window.resize(1000, 700)
    window.show()
    window.subquery_active_check.setChecked(True)
    for _ in range(4):
        window._add_subquery_row()
    QApplication.processEvents()
    QApplication.processEvents()
    assert window.width() == 1000
    assert window.dir_input.width() >= 500
    assert window.subquery_scroll.horizontalScrollBar().maximum() == 0
    assert window.subquery_scroll.verticalScrollBar().maximum() > 0
    assert window.subquery_scroll.verticalScrollBar().value() > 0


@pytest.mark.parametrize("language", ["en", "es", "gl"])
def test_directory_and_subquery_fields_fit_at_default_width(window, monkeypatch, language):
    monkeypatch.setattr(gui, "_", lambda text: gui.TRANSLATIONS.get(language, {}).get(text, text))
    localized = gui.BagheeraSearchWindow()
    try:
        localized.resize(1000, 700)
        localized.show()
        localized.subquery_active_check.setChecked(True)
        localized._add_subquery_row()
        QApplication.processEvents()
        QApplication.processEvents()
        assert localized.width() == 1000
        assert localized.dir_input.width() >= 500
        assert localized.subquery_rows[0].query_input.width() >= 160
        assert localized.subquery_scroll.horizontalScrollBar().maximum() == 0
    finally:
        localized.close()
        QApplication.processEvents()


def test_filter_order_navigation_icons_and_tooltips(window):
    window.show()
    QApplication.processEvents()
    groups = {group.title(): group for group in window.findChildren(gui.QGroupBox)}
    assert groups[gui._("Advanced")].x() < groups[gui._("Limits and Dates")].x()
    for button, label in ((window.btn_prev_page, "Previous"),
                          (window.btn_next_page, "Next")):
        assert button.text() == ""
        assert not button.icon().isNull()
        assert button.toolTip() == gui._(label)
    assert window.hide_icons_check.toolTip() == gui._("Hide Icons help")
    assert "Having:" in [label.text() for label in window.subquery_rows[0].findChildren(gui.QLabel)]


def test_having_help_buttons_follow_the_label(window, monkeypatch):
    shown = []
    monkeypatch.setattr(gui.QMessageBox, "information",
                        lambda parent, title, text: shown.append(text))
    window.subquery_active_check.setChecked(True)
    extra = window._add_subquery_row()
    window.show()
    QApplication.processEvents()
    for combo, label_text in (
        (window.having_input, gui._("Having:")),
        (window.subquery_having_input, "Having:"),
        (extra.having_input, "Having:"),
    ):
        parent = combo.parentWidget()
        labels = parent.findChildren(gui.QLabel, options=gui.Qt.FindDirectChildrenOnly)
        label = next(item for item in labels if item.text() == label_text)
        buttons = parent.findChildren(gui.QPushButton, options=gui.Qt.FindDirectChildrenOnly)
        help_button = next(button for button in buttons if button.toolTip() == gui._("Syntax Help"))
        assert label.geometry().right() < help_button.geometry().left()
        assert help_button.geometry().right() < combo.geometry().left()
        assert help_button.focusPolicy() == gui.Qt.NoFocus
        help_button.click()
    assert shown == [gui._("HAVING_EXAMPLES")] * 3
    assert window.btn_help_query.geometry().right() < window.query_input.geometry().left()
    assert window.btn_help_query.focusPolicy() == gui.Qt.NoFocus
    window.btn_help_query.click()
    assert shown[-1] == gui._("QUERY_EXAMPLES")


def test_text_clear_buttons_preserve_history(window):
    window.subquery_active_check.setChecked(True)
    row = window._add_subquery_row()
    window.show()
    combos = [window.query_input, window.dir_input, window.having_input,
              window.subquery_input, window.subquery_having_input,
              row.query_input, row.having_input]
    for combo in combos:
        combo.addItem("history")
        combo.setEditText("current")
        QApplication.processEvents()
        buttons = combo.lineEdit().findChildren(QToolButton)
        assert len(buttons) == 1
        assert buttons[0].isVisible()
        assert not buttons[0].icon().isNull()
        buttons[0].click()
        assert combo.currentText() == ""
        assert combo.findText("history") >= 0


def test_having_clear_buttons_are_visible_inside_empty_fields(window):
    window.subquery_active_check.setChecked(True)
    row = window._add_subquery_row()
    window.show()
    QApplication.processEvents()
    for combo in (window.having_input, window.subquery_having_input, row.having_input):
        combo.setEditText("")
        QApplication.processEvents()
        line_edit = combo.lineEdit()
        buttons = line_edit.findChildren(QToolButton)
        assert len(buttons) == 1
        assert buttons[0].isVisible()
        assert not buttons[0].icon().isNull()
        assert line_edit.rect().contains(buttons[0].geometry())


def test_history_buttons_use_history_icon_with_fallback(window, monkeypatch):
    calls = []
    original = gui.QIcon.fromTheme

    def from_theme(name, *args):
        calls.append(name)
        return original(name, *args)

    monkeypatch.setattr(gui.QIcon, "fromTheme", staticmethod(from_theme))
    other = gui.BagheeraSearchWindow()
    try:
        other._add_subquery_row()
        history_buttons = [
            button for button in other.findChildren(gui.QPushButton)
            if button.toolTip() == gui._("Clear History")
        ]
        assert len(history_buttons) == 7
        assert calls.count("edit-clear-history") == len(history_buttons)
        assert all(not button.icon().isNull() for button in history_buttons)
    finally:
        other.close()
        QApplication.processEvents()


@pytest.mark.parametrize("width", [1000, 1200])
def test_year_month_and_day_have_equal_width(window, width):
    window.resize(width, 700)
    window.show()
    QApplication.processEvents()
    assert window.year_combo.width() == window.month_combo.width() == window.day_combo.width()


def test_list_clear_buttons_reset_values_and_date_dependencies(window):
    window.type_combo.setCurrentIndex(1)
    window.sort_combo.setCurrentIndex(2)
    window.subquery_active_check.setChecked(True)
    row = window._add_subquery_row()
    row.operator_combo.setCurrentIndex(2)
    for combo in (window.type_combo, window.sort_combo, row.operator_combo):
        assert not combo.clear_value_button.icon().isNull()
        combo.clear_value_button.click()
        assert combo.currentIndex() == 0

    window.year_combo.setEditText("2024")
    window.month_combo.setCurrentIndex(2)
    window.day_combo.setCurrentIndex(4)
    window.month_combo.clear_value_button.click()
    assert window.month_combo.currentIndex() == 0
    assert window.day_combo.currentIndex() == 0
    assert not window.day_combo.clear_value_button.isEnabled()
    window.year_combo.clear_value_button.click()
    assert window.year_combo.currentText() == gui._("Any")
    assert not window.month_combo.isEnabled()
    assert not window.month_combo.clear_value_button.isEnabled()


def test_path_elision_tracks_column_width_and_preserves_full_path(window, monkeypatch, tmp_path):
    path = "/home/photos/very-long-collection/year/month/vacation-final-image.png"
    window.show()
    window._display_results([{"path": path, "type": "Image"}])
    table = window.results_table
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
    delegate = table.itemDelegateForColumn(1)
    displayed = []
    original = delegate.displayed_path

    def capture(text, metrics, width):
        result = original(text, metrics, width)
        displayed.append((text, QFontMetrics(metrics), width, result))
        return result

    monkeypatch.setattr(delegate, "displayed_path", capture)
    table.setColumnWidth(1, 200)
    QApplication.processEvents()
    displayed.clear()
    table.viewport().grab()
    _, metrics, width, _ = displayed[-1]
    padding = table.columnWidth(1) - width
    suffix = "/vacation-final-image.png"
    table.setColumnWidth(1, metrics.horizontalAdvance("/…" + suffix) + padding)
    QApplication.processEvents()
    displayed.clear()
    table.viewport().grab()
    text, metrics, width, short_path = displayed[-1]
    assert text == path
    assert short_path.startswith("/") and short_path.endswith(suffix)
    assert "…" in short_path
    assert metrics.horizontalAdvance(short_path) <= width

    table.setColumnWidth(1, metrics.horizontalAdvance(path) + padding)
    QApplication.processEvents()
    displayed.clear()
    table.viewport().grab()
    assert displayed[-1][3] == path
    assert table.item(0, 1).text() == path
    assert table.item(0, 1).toolTip() == path

    width = metrics.horizontalAdvance("…" + suffix)
    assert original(path, metrics, width) == "…" + suffix
    narrow = original(path, metrics, 20)
    assert metrics.horizontalAdvance(narrow) <= 20

    opened = []
    monkeypatch.setattr(gui.QDesktopServices, "openUrl",
                        lambda url: opened.append(url.toLocalFile()))
    table.setCurrentCell(0, 1)
    window._open_result()
    assert opened == [path]
    csv_path = tmp_path / "results.csv"
    monkeypatch.setattr(gui.QFileDialog, "getSaveFileName",
                        lambda *args: (str(csv_path), ""))
    window._export_to_csv()
    assert path in csv_path.read_text(encoding="utf-8")


def test_gui_runs_combined_query_with_having_and_typed_empty_subquery(window, tmp_path, monkeypatch):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    folder = tmp_path / "folder"
    folder.mkdir()
    image = folder / "image.jpg"
    image.touch()
    nested = folder / "nested"
    nested.mkdir()
    calls = []

    def execute_query(self, options):
        calls.append(dict(options))
        if options["type"] == "folder":
            return [{"id": "1", "path": str(folder)}]
        return [{"id": "2", "path": str(image)}, {"id": "3", "path": str(nested)}]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(BagheeraSearcher, "_get_item_info",
                        lambda self, item, file_id, needs: {"rating": "5"})
    monkeypatch.setattr(gui, "HAVE_BALOO_TOOLS", False)
    monkeypatch.setattr(gui.SearchWorker, "start", lambda self: self.run())
    window.hide_icons_check.setChecked(True)
    window.query_input.setEditText("album HAVING rating=5 SUBQUERY HAVING rating=5")
    window.type_combo.setCurrentIndex(window.type_combo.findData("image"))
    window.year_combo.setEditText("2025")
    window.month_combo.setCurrentIndex(7)
    window.day_combo.setCurrentIndex(14)

    window.perform_search()

    assert [call["query"] for call in calls] == ["album", ""]
    assert calls[1]["directory"] == str(folder) and calls[1]["type"] == "image"
    assert not any(key in calls[0] for key in ("year", "month", "day"))
    assert (calls[1]["year"], calls[1]["month"], calls[1]["day"]) == (2025, 7, 14)
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == str(image)


def test_gui_combines_multiple_subqueries_with_operator_precedence(window, tmp_path, monkeypatch):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    folder = tmp_path / "folder"
    folder.mkdir()
    files = [folder / f"{number}.jpg" for number in (1, 2, 3)]
    for path in files:
        path.touch()
    calls = []

    def execute_query(self, options):
        calls.append(dict(options))
        if options["type"] == "folder":
            return [{"id": "10", "path": str(folder)}]
        ids = {"first": [1, 2], "second": [2, 3], "third": [3]}[options["query"]]
        return [{"id": str(number), "path": str(files[number - 1])}
                for number in ids]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(gui, "HAVE_BALOO_TOOLS", False)
    monkeypatch.setattr(gui.SearchWorker, "start", lambda self: self.run())
    window.hide_icons_check.setChecked(True)
    window.query_input.setEditText("album SUBQUERY first")
    window.subquery_active_check.setChecked(True)
    window.subquery_input.setEditText("second")
    window.subquery_operator_combo.setCurrentIndex(
        window.subquery_operator_combo.findData("OR EXCLUSIVE"))
    third = window._add_subquery_row()
    third.query_input.setEditText("third")
    third.operator_combo.setCurrentIndex(third.operator_combo.findData("AND NOT"))
    window.type_combo.setCurrentIndex(window.type_combo.findData("image"))

    window.perform_search()

    assert [call["query"] for call in calls] == ["album", "first", "second", "third"]
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, 1).text() == str(files[0])


def test_search_worker_displays_errors(window, monkeypatch):
    class BrokenSearcher:
        def search(self, *args):
            raise ValueError("invalid HAVING")

    monkeypatch.setattr(gui, "BagheeraSearcher", BrokenSearcher)
    monkeypatch.setattr(gui.SearchWorker, "start", lambda self: self.run())
    window.query_input.setEditText("album HAVING bad")
    window.perform_search()
    assert "invalid HAVING" in window.status_label.text()
