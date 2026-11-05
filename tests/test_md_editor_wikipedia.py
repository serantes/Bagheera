import base64

import pytest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import md_editor


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
    editor = md_editor.MarkdownEditorWidget(
        tag="Travel/Xapón/Tokyo", template_text="Original"
    )

    editor.wikipedia_action.trigger()

    assert calls == [("Tokyo", editor)]
    assert editor.get_markdown_text() == "# Tokyo\n\nA summary."


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
