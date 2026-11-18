from copy import deepcopy
from types import MethodType, SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from bagheeraview.core import app as app_module


@pytest.fixture
def navigation():
    app = QApplication.instance() or QApplication([])
    window = SimpleNamespace(
        history=[], full_history=[], _navigation_history=[], _navigation_index=-1,
        btn_search_previous=QPushButton(), btn_search_next=QPushButton(),
        btn_search_refresh=QPushButton(), search_input=QComboBox(),
        status_lbl=SimpleNamespace(setText=lambda *args: None),
        progress_bar=SimpleNamespace(setRange=lambda *args: None, show=lambda: None),
        btn_load_all=SimpleNamespace(hide=lambda: None),
        btn_load_more=SimpleNamespace(hide=lambda: None),
        btn_cancel_duplicates=SimpleNamespace(hide=lambda: None),
        is_xcb=True, is_wayland=False,
        save_config=lambda: None, save_full_history=lambda: None,
        get_selected_paths=lambda: ["selected"],
    )
    window.search_input.setEditable(True)
    window.scans = []
    window.start_scan = lambda paths, **kwargs: window.scans.append((paths, kwargs))
    for name in (
            "add_to_history", "update_search_input", "_show_search_term",
            "_update_search_navigation_buttons", "_record_search_navigation",
            "_navigate_search", "process_term", "refresh_content",
            "hard_refresh_content"):
        setattr(window, name, MethodType(getattr(app_module.MainWindow, name), window))
    window.btn_search_previous.clicked.connect(lambda: window._navigate_search(-1))
    window.btn_search_next.clicked.connect(lambda: window._navigate_search(1))
    window.btn_search_refresh.clicked.connect(window.refresh_content)
    window._update_search_navigation_buttons()
    yield window
    app.processEvents()


def _combo_items(window):
    return [window.search_input.itemData(i) for i in range(window.search_input.count())]


def test_navigation_preserves_recent_history_and_nonconsecutive_duplicates(navigation):
    window = navigation
    assert not window.btn_search_previous.isEnabled()
    assert not window.btn_search_next.isEnabled()
    assert not window.btn_search_refresh.isEnabled()

    for term in ("search:/a", "search:/a", "search:/b", "search:/a"):
        window.process_term(term)
    assert window._navigation_history == ["search:/a", "search:/b", "search:/a"]
    history = list(window.history)
    full_history = deepcopy(window.full_history)
    items = _combo_items(window)

    window.btn_search_previous.click()
    assert window.scans[-1][0] == ["b"]
    assert window.search_input.currentText() == "b"
    window.btn_search_previous.click()
    assert window.scans[-1][0] == ["a"]
    assert not window.btn_search_previous.isEnabled()
    window.btn_search_next.click()
    assert window.scans[-1][0] == ["b"]
    assert window.history == history
    assert window.full_history == full_history
    assert _combo_items(window) == items

    window.search_input.setEditText("unexecuted edit")
    window.btn_search_refresh.click()
    assert window.scans[-1] == (
        ["b"], {"select_paths": ["selected"], "allow_directory_navigation": False})
    assert window.search_input.currentText() == "b"
    assert window._navigation_history == ["search:/a", "search:/b", "search:/a"]
    assert window.history == history
    assert window.full_history == full_history
    assert _combo_items(window) == items


def test_new_search_after_back_discards_forward_entries(navigation):
    window = navigation
    for term in ("search:/a", "search:/b", "search:/c"):
        window.process_term(term)
    window.btn_search_previous.click()
    window.process_term("search:/d")
    assert window._navigation_history == ["search:/a", "search:/b", "search:/d"]
    assert not window.btn_search_next.isEnabled()
    window.btn_search_previous.click()
    assert window.scans[-1][0] == ["b"]


def test_navigation_reaches_entries_evicted_from_combo(navigation):
    window = navigation
    for index in range(26):
        window.process_term(f"search:/{index}")
    assert "search:/0" not in window.history
    for _ in range(25):
        window.btn_search_previous.click()
    assert window.search_input.currentText() == "0"
    assert window.search_input.currentIndex() == -1
    assert window.scans[-1][0] == ["0"]
    assert len(window.history) == 25


def test_missing_layout_does_not_move_navigation_cursor(navigation, monkeypatch, tmp_path):
    window = navigation
    monkeypatch.setattr(app_module, "LAYOUTS_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.QMessageBox, "critical", lambda *args: None)
    window._navigation_history = ["layout:/Missing", "search:/current"]
    window._navigation_index = 1
    window._update_search_navigation_buttons()
    window.btn_search_previous.click()
    assert window._navigation_index == 1
    assert window.btn_search_previous.isEnabled()
    assert not window.btn_search_next.isEnabled()


def test_refresh_file_rescans_directory_without_changing_history(navigation, tmp_path):
    window = navigation
    path = tmp_path / "image.jpg"
    path.touch()
    term = f"file:/{path}"
    window.history = [term]
    window._record_search_navigation(term)
    window.update_search_input()
    window.search_input.setEditText("unexecuted edit")
    window.btn_search_refresh.click()
    assert window.scans == [([str(tmp_path)], {"select_paths": ["selected"]})]
    assert window.search_input.currentText() == str(path)
    assert window.history == [term]
    assert window._navigation_history == [term]


def test_hard_refresh_uses_navigated_directory(navigation, tmp_path):
    window = navigation
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    invalidated = []
    window.cache = SimpleNamespace(invalidate_directory_cache=invalidated.append)
    window.process_term(f"file:/{first}")
    window.process_term(f"file:/{second}")
    window.btn_search_previous.click()
    window.hard_refresh_content()
    assert invalidated == [str(first)]
    assert window.scans[-1][0] == [str(first)]
    assert window.history == [f"file:/{second}", f"file:/{first}"]
