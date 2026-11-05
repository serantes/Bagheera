import base64

from PySide6.QtWidgets import QMessageBox
import pytest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import constants, md_editor, wikipedia_summary
from bagheeraview.core.constants import UITexts, _UI_TEXTS


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_wikipedia_action_uses_last_tag_segment_and_replaces_text(
        qapp, monkeypatch):
    calls = []

    def select_summary(query, parent=None):
        calls.append((query, parent))
        return "# Tokyo\n\nA summary."

    monkeypatch.setattr(
        md_editor, "select_wikipedia_summary", select_summary
    )
    monkeypatch.setattr(
        QMessageBox, "exec",
        lambda dialog: (dialog.buttons()[0].click(), 0)[1],
    )
    editor = md_editor.MarkdownEditorWidget(
        tag="Travel/Xapón/Tokyo", template_text="Original"
    )

    editor.wikipedia_action.trigger()

    assert calls == [("Tokyo", editor)]
    assert editor.get_markdown_text() == "# Tokyo\n\nA summary."


def test_wikipedia_action_appends_when_user_selects_append(
        qapp, monkeypatch):
    monkeypatch.setattr(
        md_editor, "select_wikipedia_summary",
        lambda *_args, **_kwargs: "# Tokyo\n\nA summary.",
    )
    monkeypatch.setattr(
        QMessageBox, "exec",
        lambda dialog: (
            next(button for button in dialog.buttons()
                 if button.text() == UITexts.WIKIPEDIA_APPEND).click(),
            0,
        )[1],
    )
    editor = md_editor.MarkdownEditorWidget(
        tag="Travel/Xapón/Tokyo", template_text="Existing text"
    )

    editor.wikipedia_action.trigger()

    assert editor.get_markdown_text() == (
        "Existing text\n\n# Tokyo\n\nA summary."
    )


def test_wikipedia_action_cancel_keeps_existing_text(qapp, monkeypatch):
    monkeypatch.setattr(
        md_editor, "select_wikipedia_summary",
        lambda *_args, **_kwargs: "# Tokyo\n\nA summary.",
    )
    monkeypatch.setattr(
        QMessageBox, "exec",
        lambda dialog: (
            next(button for button in dialog.buttons()
                 if button.text() == UITexts.CANCEL).click(),
            0,
        )[1],
    )
    editor = md_editor.MarkdownEditorWidget(
        tag="Travel/Xapón/Tokyo", template_text="Existing text"
    )

    editor.wikipedia_action.trigger()

    assert editor.get_markdown_text() == "Existing text"


def test_wikipedia_action_keeps_text_when_selection_is_empty(
        qapp, monkeypatch):
    monkeypatch.setattr(
        md_editor, "select_wikipedia_summary", lambda *_args, **_kwargs: ""
    )
    editor = md_editor.MarkdownEditorWidget(
        tag="Travel/Xapón/Tokyo", template_text="Original"
    )

    editor.wikipedia_action.trigger()

    assert editor.get_markdown_text() == "Original"


def test_mode_button_matches_save_button_size(qapp):
    editor = md_editor.MarkdownEditorWidget(template_text="")
    save_button = editor.toolbar.widgetForAction(editor.save_action)
    mode_button = editor.toolbar.widgetForAction(editor.mode_btn)

    assert mode_button.sizeHint() == save_button.sizeHint()
    assert mode_button.size() == save_button.size()


def test_wikipedia_action_is_disabled_without_tag(qapp):
    editor = md_editor.MarkdownEditorWidget(template_text="")

    assert not editor.wikipedia_action.isEnabled()


def test_wikimedia_image_is_loaded_in_view_but_not_editor(
        qapp, monkeypatch):
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
        "/x8AAwMCAO+/r9sAAAAASUVORK5CYII="
    )
    markdown = (
        "![Tokyo](https://upload.wikimedia.org/example.png)\n\nTokyo"
    )
    calls = []

    def fetch(url):
        calls.append(url)
        return image

    monkeypatch.setattr(md_editor, "fetch_image", fetch)
    editor = md_editor.MarkdownEditorWidget(template_text=markdown)

    assert calls == ["https://upload.wikimedia.org/example.png"]
    assert "data:image/png;base64," in editor.text_area.viewer.toHtml()
    assert editor.get_markdown_text() == markdown

    editor.toggle_mode()
    assert editor.text_area.editor.toPlainText() == markdown
    assert "data:image/png" not in editor.text_area.editor.toPlainText()


@pytest.mark.parametrize("language", ["en", "es", "gl"])
def test_wikipedia_overwrite_prompt_is_translated(language):
    texts = _UI_TEXTS[language]
    assert texts["WIKIPEDIA_EXISTING_TEXT"]
    assert texts["WIKIPEDIA_APPEND"]
    assert texts["OVERWRITE"]
    assert texts["CANCEL"]


@pytest.mark.parametrize("language", ["en", "es", "gl"])
def test_wikipedia_selector_ui_is_translated(language, monkeypatch, qapp):
    monkeypatch.setattr(constants, "CURRENT_LANGUAGE", language)
    dialog = wikipedia_summary.WikipediaSelectorDialog()
    texts = constants._UI_TEXTS[language]

    assert dialog.windowTitle() == texts["WIKIPEDIA_TITLE"]
    assert dialog.query_input.placeholderText() == (
        texts["WIKIPEDIA_SEARCH_PLACEHOLDER"]
    )
    assert dialog.lang_input.placeholderText() == (
        texts["WIKIPEDIA_LANGUAGES_PLACEHOLDER"]
    )
    assert dialog.search_button.text() == texts["WIKIPEDIA_SEARCH"]
    assert [
        dialog.table.horizontalHeaderItem(i).text() for i in range(2)
    ] == [
        texts["WIKIPEDIA_LANGUAGE_COLUMN"],
        texts["WIKIPEDIA_ARTICLE_COLUMN"],
    ]
    assert dialog.accept_button.text() == texts["WIKIPEDIA_ACCEPT"]
    assert dialog.cancel_button.text() == texts["CANCEL"]
