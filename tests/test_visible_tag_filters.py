import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTabWidget

from bagheeraview.core import settings, widgets
from bagheeraview.core.settings import SettingsDialog
from bagheeraview.core.constants import UITexts


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _tag_paths(root):
    paths = []

    def visit(node, prefix=""):
        for row in range(node.rowCount()):
            child = node.child(row, 0)
            path = f"{prefix}/{child.text()}" if prefix else child.text()
            paths.append(path)
            visit(child, path)

    visit(root)
    return paths


def _tag_widget(monkeypatch, whitelist, blacklist, files, tmp_path):
    monkeypatch.setattr(
        widgets.TagEditWidget, "load_available_tags", lambda self: None)
    monkeypatch.setattr(
        widgets, "TAG_INFO_DB_PATH", str(tmp_path / "tag-info-db"))
    monkeypatch.setitem(widgets.APP_CONFIG, "visible_tags_whitelist", whitelist)
    monkeypatch.setitem(widgets.APP_CONFIG, "visible_tags_blacklist", blacklist)
    tag_widget = widgets.TagEditWidget()
    tag_widget.available_tags = [
        "animals", "animals/cat", "animals/private",
        "animals/private/cat", "plants/tree",
    ]
    tag_widget.set_files_data(files)
    return tag_widget


def test_filters_all_tags_but_keeps_all_used_tags(qapp, monkeypatch, tmp_path):
    tag_widget = _tag_widget(
        monkeypatch,
        [r"^animals(?:/.*)?$"],
        [r"^animals/private(?:/.*)?$"],
        {"image.jpg": {"animals/private/cat", "plants/tree"}},
        tmp_path,
    )

    assert _tag_paths(tag_widget.root_all) == ["animals", "animals/cat"]
    assert _tag_paths(tag_widget.root_favs) == [
        "animals", "animals/private", "animals/private/cat",
        "plants", "plants/tree",
    ]
    assert tag_widget.available_tags == [
        "animals", "animals/cat", "animals/private",
        "animals/private/cat", "plants/tree",
    ]


def test_excluded_parent_hides_descendants(qapp, monkeypatch, tmp_path):
    tag_widget = _tag_widget(
        monkeypatch, [r"^animals/cat$"], [],
        {"image.jpg": {"animals/cat"}},
        tmp_path,
    )

    assert _tag_paths(tag_widget.root_all) == []
    assert _tag_paths(tag_widget.root_favs) == ["animals", "animals/cat"]


def test_empty_whitelist_includes_all_unless_blacklisted(
        qapp, monkeypatch, tmp_path):
    tag_widget = _tag_widget(
        monkeypatch, [], [r"^plants(/.*)?$"], {}, tmp_path)

    assert _tag_paths(tag_widget.root_all) == [
        "animals", "animals/cat", "animals/private",
        "animals/private/cat",
    ]


def test_refresh_preserves_pending_tag_changes(qapp, monkeypatch, tmp_path):
    tag_widget = _tag_widget(
        monkeypatch, [], [], {"image.jpg": set()}, tmp_path)
    cat = tag_widget.item_mapping["animals/cat"][0]
    cat.setCheckState(Qt.Checked)

    monkeypatch.setitem(
        widgets.APP_CONFIG, "visible_tags_whitelist", [r"^animals(/.*)?$"])
    tag_widget.refresh_visible_tag_filters()

    assert tag_widget.item_mapping["animals/cat"][0].checkState() == Qt.Checked
    assert "animals/cat" in tag_widget.manually_changed


def test_settings_places_visible_tags_next_to_quick_tags(qapp, monkeypatch):
    monkeypatch.setitem(widgets.APP_CONFIG, "visible_tags_whitelist", [])
    monkeypatch.setitem(widgets.APP_CONFIG, "visible_tags_blacklist", [])
    dialog = SettingsDialog()
    outer_tabs = dialog.layout().itemAt(0).widget()

    assert isinstance(outer_tabs, QTabWidget)
    labels = [outer_tabs.tabText(i) for i in range(outer_tabs.count())]
    viewer_index = labels.index(UITexts.SETTINGS_GROUP_VIEWER)
    tags_index = labels.index(UITexts.SETTINGS_GROUP_TAGS)
    regions_index = labels.index(UITexts.SETTINGS_GROUP_AREAS)
    assert viewer_index < tags_index < regions_index
    assert [
        dialog.tags_sub_tabs.tabText(i)
        for i in range(dialog.tags_sub_tabs.count())
    ] == [UITexts.VIEWER_MENU_TAGS, UITexts.SETTINGS_VISIBLE_TAGS_TAB]
    dialog.close()


def test_settings_rejects_invalid_regular_expressions(qapp, monkeypatch):
    dialog = SettingsDialog()
    dialog.visible_tags_whitelist_edit.setPlainText("[")
    warnings = []
    monkeypatch.setattr(
        settings.QMessageBox, "warning",
        lambda *args: warnings.append(args))

    dialog.accept()

    assert len(warnings) == 1
    assert warnings[0][1] == UITexts.SETTINGS_VISIBLE_TAGS_INVALID_TITLE
    dialog.close()
