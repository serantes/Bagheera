import pytest
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from bagheeraview.core import constants
from bagheeraview.core.tag_information import get_tag_information_store
from bagheeraview.core.tag_information_editor import (
    TagInfoSearchDialog,
    TagInformationEditor,
    TemplateNameDialog,
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    return get_tag_information_store(str(tmp_path / "tag-info-db"))


def test_tags_share_one_information_record_and_delete_when_unreferenced(store):
    first_key = store.save_info("Travel/Tokyo", "Tokyo notes")
    assert store.associate("Places/Tokyo", "Travel/Tokyo")
    assert store.get_info_key("Places/Tokyo") == first_key

    store.save_info("Places/Tokyo", "Updated notes")
    assert store.get_info("Travel/Tokyo") == "Updated notes"

    assert store.delete_tag("Travel/Tokyo")
    assert store.get_info("Places/Tokyo") == "Updated notes"
    assert store.delete_tag("Places/Tokyo")
    assert not store.tags_with_info()


def test_templates_and_tag_search(store):
    store.save_template("Travel", "# Travel")
    store.save_info("Travel/Japan", "Japan notes")
    store.save_info("People/Japan", "People notes")

    assert store.templates() == ["Travel"]
    assert store.get_template("Travel") == "# Travel"
    assert store.tags_with_info("jApAn") == [
        "People/Japan", "Travel/Japan"
    ]
    assert store.delete_template("Travel")
    assert store.templates() == []


def test_legacy_migration_imports_unambiguous_files_and_preserves_ambiguity(
        tmp_path, store):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "Travel_Tokyo.md").write_text("Tokyo", encoding="utf-8")
    ambiguous = legacy / "Places_Tokyo.md"
    ambiguous.write_text("Ambiguous", encoding="utf-8")
    template = tmp_path / "tag_info_template.md"
    template.write_text("# Template", encoding="utf-8")

    imported, unresolved = store.migrate_legacy(
        str(legacy),
        str(template),
        ["Travel/Tokyo", "Places/Tokyo", "Places_Tokyo"],
    )

    assert imported == ["Travel/Tokyo"]
    assert unresolved == [str(ambiguous)]
    assert store.get_info("Travel/Tokyo") == "Tokyo"
    assert store.get_template("tag_info_template") == "# Template"
    assert ambiguous.read_text(encoding="utf-8") == "Ambiguous"


def test_legacy_migration_does_not_restore_deleted_data(tmp_path, store):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "Travel_Tokyo.md").write_text("Tokyo", encoding="utf-8")
    template = tmp_path / "tag_info_template.md"
    template.write_text("# Template", encoding="utf-8")
    known_tags = ["Travel/Tokyo", "Places/Tokyo", "Places_Tokyo"]

    store.migrate_legacy(str(legacy), str(template), known_tags)
    assert store.delete_template("tag_info_template")
    assert store.delete_tag("Travel/Tokyo")

    imported, _unresolved = store.migrate_legacy(
        str(legacy), str(template), known_tags
    )

    assert imported == []
    assert store.get_template("tag_info_template") is None
    assert store.get_info("Travel/Tokyo") is None


def test_editor_has_two_toolbars_and_saves_tag_information(qapp, store):
    editor = TagInformationEditor("Travel/Tokyo", store)
    editor.editor.set_markdown_text("Tokyo notes")

    editor._save_tag_info()

    assert store.get_info("Travel/Tokyo") == "Tokyo notes"
    assert editor._saved_text == "Tokyo notes"
    assert not editor.editor.format_toolbar.isHidden()
    assert editor.editor.toolbar.isHidden()
    editor_layout = editor.editor.layout()
    assert editor_layout.itemAt(0).widget() is editor.editor.toolbar
    assert editor_layout.itemAt(1).widget() is editor.editor.format_toolbar
    assert editor_layout.itemAt(2).widget() is editor.editor.text_area
    assert not editor.new_action.icon().isNull()
    assert not editor.save_action.icon().isNull()
    assert not editor.delete_action.icon().isNull()
    assert not editor.search_action.icon().isNull()


def test_editor_new_and_template_load_only_change_document(qapp, store):
    store.save_info("Travel/Tokyo", "Saved tag info")
    store.save_template("Travel", "# Template")
    editor = TagInformationEditor("Travel/Tokyo", store)

    editor._load_template("Travel")
    assert editor.editor.get_markdown_text() == "# Template"
    assert store.get_info("Travel/Tokyo") == "Saved tag info"

    editor._new_document()
    assert editor.editor.get_markdown_text() == ""


def test_escape_closes_after_unsaved_changes_confirmation(
        qapp, store, monkeypatch):
    editor = TagInformationEditor("Travel/Tokyo", store)
    editor.show()
    editor.editor.set_markdown_text("Unsaved text")
    response = [constants.UITexts.CANCEL]

    def answer_confirmation(box):
        next(button for button in box.buttons()
             if button.text() == response[0]).click()
        return 0

    monkeypatch.setattr(
        QMessageBox, "exec", answer_confirmation
    )

    editor.escape_action.trigger()
    qapp.processEvents()
    assert editor.isVisible()

    assert editor.escape_action.shortcut() == QKeySequence(
        Qt.Key.Key_Escape
    )

    response[0] = constants.UITexts.TAG_INFO_DISCARD
    editor.escape_action.trigger()
    qapp.processEvents()

    assert not editor.isVisible()


def test_web_search_defaults_to_duckduckgo_and_uses_tag_leaf(
        qapp, store, monkeypatch):
    editor = TagInformationEditor("a/b/c", store)
    opened_urls = []
    monkeypatch.setattr(
        "bagheeraview.core.tag_information_editor.QDesktopServices.openUrl",
        lambda url: opened_urls.append(url) or True,
    )

    editor.web_search_action.trigger()

    assert editor.edit_action.text() == constants.UITexts.TAG_INFO_EDIT
    assert editor.web_search_button.text() == constants.UITexts.TAG_INFO_WEB_SEARCH
    assert opened_urls == [QUrl("https://duckduckgo.com/?q=c")]


def test_web_search_menu_can_choose_other_search_engines(
        qapp, store, monkeypatch):
    editor = TagInformationEditor("a/b/c", store)
    opened_urls = []
    monkeypatch.setattr(
        "bagheeraview.core.tag_information_editor.QDesktopServices.openUrl",
        lambda url: opened_urls.append(url) or True,
    )

    engines = [action.text() for action in editor.web_search_button.menu().actions()]
    google_action = next(
        action for action in editor.web_search_button.menu().actions()
        if action.text() == "Google"
    )
    google_action.trigger()

    assert engines == ["DuckDuckGo", "Google", "Bing", "Yahoo", "Brave", "Ecosia"]
    assert opened_urls == [QUrl("https://www.google.com/search?q=c")]


def test_save_as_template_does_not_save_tag_information(
        qapp, store, monkeypatch):
    store.save_info("Travel/Tokyo", "Persisted tag text")
    editor = TagInformationEditor("Travel/Tokyo", store)
    editor.editor.set_markdown_text("Template text")
    monkeypatch.setattr(
        TemplateNameDialog, "exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    monkeypatch.setattr(
        TemplateNameDialog, "template_name", lambda _dialog: "Example"
    )

    editor._save_as_template()

    assert store.get_template("Example") == "Template text"
    assert store.get_info("Travel/Tokyo") == "Persisted tag text"


def test_delete_tag_action_removes_only_current_association(
        qapp, store, monkeypatch):
    store.save_info("Travel/Tokyo", "Shared")
    store.associate("Places/Tokyo", "Travel/Tokyo")
    editor = TagInformationEditor("Travel/Tokyo", store)
    monkeypatch.setattr(editor, "_confirm", lambda *_args: True)

    editor._delete_tag_info()

    assert store.get_info("Travel/Tokyo") is None
    assert store.get_info("Places/Tokyo") == "Shared"
    assert editor.editor.get_markdown_text() == ""


def test_search_dialog_filters_available_tags(qapp, store):
    store.save_info("Travel/Tokyo", "Tokyo")
    store.save_info("Travel/Osaka", "Osaka")
    dialog = TagInfoSearchDialog(store)

    dialog.filter_edit.setText("TOK")

    assert dialog.tag_list.count() == 1
    assert dialog.tag_list.item(0).text() == "Travel/Tokyo"


def test_search_reassociates_current_tag_with_confirmed_target(
        qapp, store, monkeypatch):
    store.save_info("Travel/Tokyo", "Tokyo")
    store.save_info("Places/Tokyo", "Place info")
    editor = TagInformationEditor("Travel/Tokyo", store)

    class SelectedTagDialog:
        def __init__(self, _store, _parent):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_tag(self):
            return "Places/Tokyo"

    monkeypatch.setattr(
        "bagheeraview.core.tag_information_editor.TagInfoSearchDialog",
        SelectedTagDialog,
    )
    monkeypatch.setattr(
        QMessageBox, "exec",
        lambda box: (
            next(button for button in box.buttons()
                 if button.text() == constants.UITexts.TAG_INFO_YES).click(),
            0,
        )[1],
    )

    editor._find_tag()

    assert store.get_info("Travel/Tokyo") == "Place info"
    assert store.get_info_key("Travel/Tokyo") == store.get_info_key(
        "Places/Tokyo"
    )


@pytest.mark.parametrize("language", ["en", "es", "gl"])
def test_tag_information_texts_are_translated(language):
    strings = constants._UI_TEXTS[language]
    assert strings["TAG_INFO_NEW"]
    assert strings["TAG_INFO_SAVE"]
    assert strings["TAG_INFO_SAVE_AS_TEMPLATE"]
    assert strings["TAG_INFO_DELETE"]
    assert strings["TAG_INFO_FIND"]
    assert strings["TAG_INFO_WEB_SEARCH"]
    assert strings["WIKIPEDIA_TAG_TOOLTIP"]
