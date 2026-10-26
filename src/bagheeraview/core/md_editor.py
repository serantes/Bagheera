#!/usr/bin/env python3
"""Dual-mode Markdown editor: rendered view and plain text editing.

The module can be used in two ways.

Standalone::

    python md_editor.py [file.md]

Embedded in another PySide6 project::

    from md_editor import MarkdownEditorWidget

    editor = MarkdownEditorWidget(filepath="notes.md")
    layout.addWidget(editor)
    editor.status_message.connect(statusbar.showMessage)
    text = editor.get_markdown_text()

Importing the module has no side effects: no ``QApplication`` is created
and nothing is shown until ``main()`` is called.
"""

import os
import re
import sys
from typing import Callable, List, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QKeySequence,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

__all__ = [
    "DualModeMarkdownWidget",
    "MainWindow",
    "MarkdownEditorWidget",
    "PROFILE_TEMPLATE",
    "PlainTextEdit",
    "main",
]

EDITOR_FONT_SIZE = 10
WEB_SCHEMES = ("http", "https", "mailto")
HEADING_MARKER = re.compile(r"^#{1,6} ")
BULLET_MARKER = re.compile(r"^- ")
NUMBER_MARKER = re.compile(r"^\d+\. ")
QUOTE_MARKER = re.compile(r"^> ")
PROFILE_TEMPLATE = (
    ""
)


class PlainTextEdit(QPlainTextEdit):
    """Plain text editor with a fixed font that cannot be zoomed.

    ``QPlainTextEdit`` stores and pastes only unformatted text, so no
    colors, styles or rich content can ever enter the document. Undo and
    redo (Ctrl+Z, Ctrl+Y, Ctrl+Shift+Z) are built in.
    """

    def __init__(self, font: QFont, parent: Optional[QWidget] = None):
        """Create the editor with a fixed font.

        Args:
            font: The font and size used for all the text.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setFont(font)
        self.document().setDefaultFont(font)

        # A style sheet takes precedence over the application font and
        # style, so the font cannot be altered from outside.
        self.setStyleSheet(
            "QPlainTextEdit {"
            f" font-family: '{font.family()}';"
            f" font-size: {font.pointSize()}pt;"
            " }"
        )

    def wheelEvent(self, event):
        """Ignore Ctrl+wheel so the font size is never changed.

        Args:
            event: The wheel event.
        """
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            event.ignore()
            return
        super().wheelEvent(event)

    @staticmethod
    def _qt_len(text: str) -> int:
        """Return the length of ``text`` in Qt units (UTF-16 code units).

        Args:
            text: Any string.

        Returns:
            The number of UTF-16 code units, which is what Qt uses for
            cursor positions.
        """
        return len(text.encode("utf-16-le")) // 2

    def _replace_selection(
        self, new_text: str, select_offset: int, select_text: str
    ):
        """Replace the selection and select part of the new text.

        The whole change is a single undo step.

        Args:
            new_text: Text that replaces the current selection.
            select_offset: Offset in ``new_text`` where the new selection
                starts, in characters.
            select_text: The part of ``new_text`` to select afterwards.
        """
        cursor = self.textCursor()
        start = cursor.selectionStart()
        cursor.beginEditBlock()
        cursor.insertText(new_text)
        cursor.endEditBlock()

        begin = start + self._qt_len(new_text[:select_offset])
        cursor.setPosition(begin)
        cursor.setPosition(
            begin + self._qt_len(select_text),
            QTextCursor.MoveMode.KeepAnchor,
        )
        self.setTextCursor(cursor)

    def _selected_text(self) -> str:
        """Return the selected text with ``\\n`` as line separator.

        Returns:
            The selected text, or an empty string.
        """
        return self.textCursor().selectedText().replace("\u2029", "\n")

    def wrap_selection(self, before: str, after: str, placeholder: str):
        """Wrap the selection with Markdown markers, or unwrap it.

        With no selection, ``placeholder`` is inserted between the markers
        and selected. If the selection already starts with ``before`` and
        ends with ``after``, the markers are removed instead.

        Args:
            before: Marker inserted before the text.
            after: Marker inserted after the text.
            placeholder: Text used when nothing is selected.
        """
        selected = self._selected_text()
        wrapped = (
            len(selected) >= len(before) + len(after)
            and selected.startswith(before)
            and selected.endswith(after)
        )
        if wrapped:
            inner = selected[len(before):len(selected) - len(after)]
            self._replace_selection(inner, 0, inner)
        else:
            inner = selected or placeholder
            self._replace_selection(
                before + inner + after, len(before), inner
            )

    def _target_blocks(self) -> list:
        """Return the non-blank lines touched by the selection.

        Returns:
            The text blocks to format. If every touched line is blank,
            all of them are returned.
        """
        cursor = self.textCursor()
        document = self.document()
        first = document.findBlock(cursor.selectionStart())
        last = document.findBlock(cursor.selectionEnd())
        if (
            cursor.hasSelection()
            and last.blockNumber() != first.blockNumber()
            and cursor.selectionEnd() == last.position()
        ):
            # The selection ends at the very start of a line: ignore it.
            last = last.previous()

        blocks = []
        block = first
        while block.isValid():
            blocks.append(block)
            if block.blockNumber() == last.blockNumber():
                break
            block = block.next()

        return [blk for blk in blocks if blk.text().strip()] or blocks

    def toggle_line_prefix(
        self, make_prefix: Callable[[int], str], marker: "re.Pattern"
    ):
        """Add, replace or remove a Markdown prefix on the selected lines.

        If every line already has exactly the requested prefix, the prefix
        is removed. Otherwise any existing marker is replaced.

        Args:
            make_prefix: Function that gives the prefix for the n-th line
                of the selection, starting at 0.
            marker: Pattern that matches an existing prefix of the same
                kind at the start of a line.
        """
        blocks = self._target_blocks()
        prefixes = [make_prefix(index) for index in range(len(blocks))]

        def existing(block) -> str:
            match = marker.match(block.text())
            return match.group(0) if match else ""

        remove_all = all(
            existing(block) == prefix
            for block, prefix in zip(blocks, prefixes)
        )

        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block, prefix in zip(blocks, prefixes):
            edit = QTextCursor(block)
            old = existing(block)
            if old:
                edit.movePosition(
                    QTextCursor.MoveOperation.NextCharacter,
                    QTextCursor.MoveMode.KeepAnchor,
                    len(old),
                )
                edit.removeSelectedText()
            if not remove_all:
                edit.insertText(prefix)
        cursor.endEditBlock()

    def set_heading(self, level: int):
        """Turn the selected lines into headings of the given level.

        Args:
            level: Heading level, from 1 to 6.
        """
        prefix = "#" * level + " "
        self.toggle_line_prefix(lambda _index: prefix, HEADING_MARKER)

    def toggle_bullet_list(self):
        """Toggle a bullet list on the selected lines."""
        self.toggle_line_prefix(lambda _index: "- ", BULLET_MARKER)

    def toggle_numbered_list(self):
        """Toggle a numbered list on the selected lines."""
        self.toggle_line_prefix(
            lambda index: f"{index + 1}. ", NUMBER_MARKER
        )

    def toggle_quote(self):
        """Toggle a block quote on the selected lines."""
        self.toggle_line_prefix(lambda _index: "> ", QUOTE_MARKER)

    def insert_link(self):
        """Insert a Markdown link and select its address.

        The selected text, if any, becomes the link text.
        """
        text = self._selected_text() or "link text"
        address = "https://"
        self._replace_selection(
            f"[{text}]({address})", len(text) + 3, address
        )

    def insert_code_block(self):
        """Wrap the selection in a fenced code block, or unwrap it."""
        cursor = self.textCursor()
        block = self.document().findBlock(cursor.selectionStart())
        at_line_start = cursor.selectionStart() == block.position()
        before = "```\n" if at_line_start else "\n```\n"
        self.wrap_selection(before, "\n```", "code")

    def insert_rule(self):
        """Insert a horizontal rule after the current line."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertText("\n\n---\n")
        self.setTextCursor(cursor)


class DualModeMarkdownWidget(QStackedWidget):
    """Widget that toggles between rendered Markdown and plain text editing.

    In view mode the Markdown is rendered read-only in a ``QTextBrowser``
    and links are clickable. In edit mode a separate ``QPlainTextEdit``
    shows the raw Markdown as pure plain text with a fixed monospace font
    and size: no formatting and no colors. Because the two modes use
    different widgets, nothing from the rendered view can leak into the
    editor.

    Attributes:
        raw_markdown: Last known Markdown source of the document.
        edit_mode: True while the widget is in plain text edit mode.
        viewer: The ``QTextBrowser`` used in view mode.
        editor: The ``PlainTextEdit`` used in edit mode.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the widget in view mode.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.raw_markdown = ""
        self.edit_mode = False

        edit_font = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        )
        edit_font.setPointSize(EDITOR_FONT_SIZE)

        self.viewer = QTextBrowser()
        self.editor = PlainTextEdit(edit_font)
        self.addWidget(self.viewer)
        self.addWidget(self.editor)

        # Links are handled manually in ``_on_anchor_clicked`` so that
        # local files never replace the document content.
        self.viewer.setOpenLinks(False)
        self.viewer.setOpenExternalLinks(False)
        self.viewer.anchorClicked.connect(self._on_anchor_clicked)

        self.set_view_mode()

    def get_markdown_text(self) -> str:
        """Return the current Markdown source, including unsaved edits.

        Returns:
            The Markdown text of the document.
        """
        if self.edit_mode:
            self.raw_markdown = self.editor.toPlainText()
        return self.raw_markdown

    def set_markdown_text(self, text: str):
        """Replace the document with ``text``, keeping the current mode.

        Args:
            text: The new Markdown source.
        """
        self.raw_markdown = text
        if self.edit_mode:
            self.set_edit_mode()
        else:
            self.set_view_mode()

    def _release_selection_and_focus(self):
        """Deselect any selected text and remove focus from the viewer."""
        cursor = self.viewer.textCursor()
        cursor.clearSelection()
        self.viewer.setTextCursor(cursor)
        self.viewer.clearFocus()
        self.editor.clearFocus()

    def set_view_mode(self):
        """Switch to the rendered Markdown view with clickable links."""
        if self.edit_mode:
            self.raw_markdown = self.editor.toPlainText()

        self._release_selection_and_focus()

        self.edit_mode = False
        self.viewer.setMarkdown(self.raw_markdown)
        self.setCurrentWidget(self.viewer)

    def set_edit_mode(self):
        """Switch to plain text editing with a fixed monospace font.

        Before switching, any selected text is deselected and the widgets
        lose focus, which avoids rendering glitches from the view mode.
        Loading the text resets the undo history, so the user can only
        undo their own edits.
        """
        self._release_selection_and_focus()

        self.edit_mode = True
        self.editor.setPlainText(self.raw_markdown)

        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.editor.setTextCursor(cursor)
        self.setCurrentWidget(self.editor)

    def toggle_mode(self) -> bool:
        """Toggle between view and edit modes.

        Returns:
            True if the widget is now in edit mode, False otherwise.
        """
        if self.edit_mode:
            self.set_view_mode()
        else:
            self.set_edit_mode()
        return self.edit_mode

    def _on_anchor_clicked(self, url: QUrl):
        """Open web links externally and report local file links.

        Args:
            url: The link that was clicked in the rendered view.
        """
        if url.scheme() in WEB_SCHEMES:
            QDesktopServices.openUrl(url)
        else:
            QMessageBox.information(
                self,
                "Local File Detected",
                f"Accessing file path:\n{url.toLocalFile() or url.toString()}",
            )


class MarkdownEditorWidget(QWidget):
    """Reusable editor with toolbar, dual-mode text area and file handling.

    It is a plain ``QWidget``, so it can be placed in any layout, dialog or
    main window. It never touches the host application: user feedback is
    published through signals instead of a status bar.

    If ``filepath`` exists, its content is loaded. Otherwise the editor
    starts with a template, chosen in this order: the content of
    ``template_file`` if it exists, then ``template_text`` if given, and
    finally ``PROFILE_TEMPLATE``.

    Signals:
        status_message(str, int): Message and timeout in milliseconds.
        file_loaded(str): Emitted with the path after a file is loaded.
        file_saved(str): Emitted with the path after a file is saved.
        mode_changed(bool): Emitted with True when entering edit mode.

    Attributes:
        text_area: The inner ``DualModeMarkdownWidget``.
        toolbar: The toolbar with the save, mode and Markdown
            formatting controls.
        save_action: The save action. A host that already uses Ctrl+S can
            free the shortcut with ``save_action.setShortcut(QKeySequence())``.
        filepath: Path of the current document, or None.

    While the editor is shown and ``capture_keys`` is True, it keeps all
    key presses and shortcuts for itself. Only Ctrl+Q is passed on, and
    the editor's own shortcuts (save, bold, italic, link) keep working.
    System shortcuts such as Alt+Tab cannot be captured by any
    application.

    When the window that contains the editor is closed, the user is asked
    about unsaved changes automatically, and the window stays open if
    they cancel. A host does not need extra code for this, but it can
    call ``maybe_save`` or ``has_unsaved_changes`` itself, for example
    before closing a tab.
    """

    status_message = Signal(str, int)
    file_loaded = Signal(str)
    file_saved = Signal(str)
    mode_changed = Signal(bool)

    def __init__(
        self,
        filepath: Optional[str] = None,
        template_text: Optional[str] = None,
        template_file: Optional[str] = None,
        parent: Optional[QWidget] = None,
        show_toolbar: bool = True,
        auto_load: bool = True,
        capture_keys: bool = True,
    ):
        """Create the editor.

        Args:
            filepath: Optional path of a Markdown file to open.
            template_text: Optional Markdown text used as template instead
                of ``PROFILE_TEMPLATE``. An empty string gives an empty
                editor.
            template_file: Optional path of a file whose content is used
                as template when it exists.
            parent: Optional parent widget.
            show_toolbar: Whether to show the built-in toolbar. The
                ``save_file`` and ``toggle_mode`` methods stay available
                when it is hidden.
            auto_load: Whether to load the document on creation. Pass
                False to connect signals first and call ``load_file``
                later.
            capture_keys: Whether the editor takes every key press while
                it is shown, so the host application cannot react to
                them. Ctrl+Q is always left to the host.
        """
        super().__init__(parent)
        self.capture_keys = capture_keys
        self.filepath = filepath
        self.template_text = template_text
        self.template_file = template_file
        # Text as last loaded or saved, to detect unsaved changes.
        self._saved_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_area = DualModeMarkdownWidget()
        self.toolbar = self._create_toolbar()
        self.toolbar.setVisible(show_toolbar)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.text_area)

        self._install_event_filter()

        if auto_load:
            self.load_file()

    def _create_toolbar(self) -> QToolBar:
        """Create the toolbar with save, mode and formatting controls.

        Returns:
            The configured toolbar.
        """
        toolbar = QToolBar("Main Toolbar", self)

        self.save_action = QAction("💾", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setToolTip("Save the document (Ctrl+S)")
        self.save_action.triggered.connect(self.save_file)
        toolbar.addAction(self.save_action)
        # Also register it on the widget so the shortcut keeps working
        # when the toolbar is hidden.
        self.addAction(self.save_action)

        toolbar.addSeparator()

        self.mode_btn = QPushButton("👁️")
        self.mode_btn.setToolTip("Switch to Edit Mode (plain text)")
        self.mode_btn.setCheckable(True)
        self.mode_btn.clicked.connect(self.toggle_mode)
        toolbar.addWidget(self.mode_btn)

        self._format_actions: List[QAction] = []
        self._add_format_actions(toolbar)
        self._set_format_enabled(False)
        return toolbar

    def _add_format_actions(self, toolbar: QToolBar):
        """Add the Markdown formatting buttons to the toolbar.

        The buttons only work in edit mode and are disabled otherwise.

        Args:
            toolbar: The toolbar that receives the buttons.
        """
        editor = self.text_area.editor
        groups = [
            [
                ("B", "Bold (Ctrl+B)", "Ctrl+B", "bold",
                 lambda: editor.wrap_selection("**", "**", "bold text")),
                ("I", "Italic (Ctrl+I)", "Ctrl+I", "italic",
                 lambda: editor.wrap_selection("*", "*", "italic text")),
                ("S", "Strikethrough", None, "strike",
                 lambda: editor.wrap_selection("~~", "~~", "text")),
                ("<>", "Inline code", None, None,
                 lambda: editor.wrap_selection("`", "`", "code")),
            ],
            [
                ("H1", "Heading 1", None, None,
                 lambda: editor.set_heading(1)),
                ("H2", "Heading 2", None, None,
                 lambda: editor.set_heading(2)),
                ("H3", "Heading 3", None, None,
                 lambda: editor.set_heading(3)),
            ],
            [
                ("• List", "Bullet list", None, None,
                 editor.toggle_bullet_list),
                ("1. List", "Numbered list", None, None,
                 editor.toggle_numbered_list),
                ("❝ Quote", "Block quote", None, None,
                 editor.toggle_quote),
            ],
            [
                ("🔗 Link", "Link (Ctrl+K)", "Ctrl+K", None,
                 editor.insert_link),
                ("{ } Block", "Code block", None, None,
                 editor.insert_code_block),
                ("― Rule", "Horizontal rule", None, None,
                 editor.insert_rule),
            ],
        ]

        for group in groups:
            toolbar.addSeparator()
            for label, tip, shortcut, style, callback in group:
                self._add_format_action(
                    toolbar, label, tip, shortcut, style, callback
                )

    def _add_format_action(
        self,
        toolbar: QToolBar,
        label: str,
        tooltip: str,
        shortcut: Optional[str],
        style: Optional[str],
        callback: Callable[[], None],
    ):
        """Create one formatting action and add it to the toolbar.

        Args:
            toolbar: The toolbar that receives the button.
            label: Text of the button.
            tooltip: Tooltip of the button.
            shortcut: Optional key sequence, active while the focus is
                inside the editor.
            style: ``"bold"``, ``"italic"``, ``"strike"`` or None; the
                font style of the button text.
            callback: Function that applies the formatting.
        """
        action = QAction(label, self)
        action.setToolTip(tooltip)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut
            )
        action.triggered.connect(
            lambda _checked=False: self._apply_format(callback)
        )
        toolbar.addAction(action)
        # Also register it on the widget so the shortcut keeps working
        # when the toolbar is hidden.
        self.addAction(action)
        self._format_actions.append(action)

        button = toolbar.widgetForAction(action)
        if button is not None and style:
            font = button.font()
            font.setBold(style == "bold")
            font.setItalic(style == "italic")
            font.setStrikeOut(style == "strike")
            button.setFont(font)

    def _apply_format(self, callback: Callable[[], None]):
        """Run a formatting function and return the focus to the editor.

        Args:
            callback: Function that applies the formatting.
        """
        if not self.text_area.edit_mode:
            return
        callback()
        self.text_area.editor.setFocus()

    def _set_format_enabled(self, enabled: bool):
        """Enable or disable all the formatting actions.

        Args:
            enabled: True to enable them, False to disable them.
        """
        for action in self._format_actions:
            action.setEnabled(enabled)

    def get_markdown_text(self) -> str:
        """Return the current Markdown source, including unsaved edits.

        Returns:
            The Markdown text of the document.
        """
        return self.text_area.get_markdown_text()

    def set_markdown_text(self, text: str):
        """Replace the document content, keeping the current mode.

        Args:
            text: The new Markdown source.
        """
        self.text_area.set_markdown_text(text)

    def toggle_mode(self) -> bool:
        """Toggle between view and edit modes and update the toolbar.

        Returns:
            True if the editor is now in edit mode, False otherwise.
        """
        is_editing = self.text_area.toggle_mode()
        self.mode_btn.setChecked(is_editing)
        self._set_format_enabled(is_editing)
        if is_editing:
            self.mode_btn.setText("📖")
            self.mode_btn.setToolTip(
                "Switch to View Mode (rendered Markdown)"
            )
            self.status_message.emit("Edit mode activated (Plain text)", 2000)
        else:
            self.mode_btn.setText("👁️")
            self.mode_btn.setToolTip("Switch to Edit Mode (plain text)")
            self.status_message.emit(
                "View mode activated (Rendered Markdown)", 2000
            )
        self.mode_changed.emit(is_editing)
        return is_editing

    def get_template(self) -> str:
        """Return the template used when there is no document to load.

        Returns:
            The content of ``template_file`` if it exists and is readable,
            else ``template_text`` if it was given, else
            ``PROFILE_TEMPLATE``.
        """
        if self.template_file and os.path.exists(self.template_file):
            try:
                with open(self.template_file, "r", encoding="utf-8") as obj:
                    return obj.read()
            except (OSError, UnicodeDecodeError) as exception:
                QMessageBox.warning(
                    self,
                    "Template Error",
                    f"Could not read the template file:\n{exception}",
                )

        if self.template_text is not None:
            return self.template_text
        return PROFILE_TEMPLATE

    def load_file(self, path: Optional[str] = None) -> bool:
        """Load the document if it exists; otherwise load the template.

        Args:
            path: Optional new document path. If omitted, the current
                ``filepath`` is used.

        Returns:
            True if the document was read from a file, False if the
            template was loaded or the file could not be read.
        """
        if path is not None:
            self.filepath = path

        if self.filepath and os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as file_obj:
                    content = file_obj.read()
            except (OSError, UnicodeDecodeError) as exception:
                QMessageBox.critical(
                    self, "Error", f"Could not read the file:\n{exception}"
                )
                return False

            self.set_markdown_text(content)
            self._saved_text = self.get_markdown_text()
            self.status_message.emit(f"File loaded: {self.filepath}", 4000)
            self.file_loaded.emit(self.filepath)
            return True

        self.set_markdown_text(self.get_template())
        self._saved_text = self.get_markdown_text()
        return True

    def save_file(self, path: Optional[str] = None) -> bool:
        """Save the document, asking for a path if none is known.

        Args:
            path: Optional target path. If omitted, the current
                ``filepath`` is used, or a save dialog is shown.

        Returns:
            True if the document was saved, False if the user cancelled
            the dialog or the file could not be written.
        """
        target = path or self.filepath
        if not target:
            target, _ = QFileDialog.getSaveFileName(
                self,
                "Save Markdown File",
                "",
                "Markdown Files (*.md);;All Files (*)",
            )
            if not target:
                return False

        text = self.get_markdown_text()
        try:
            with open(target, "w", encoding="utf-8") as file_obj:
                file_obj.write(text)
        except OSError as exception:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Could not write to the file:\n{exception}",
            )
            return False

        self.filepath = target
        self._saved_text = text
        self.status_message.emit(f"Changes saved to: {target}", 4000)
        self.file_saved.emit(target)
        return True

    @staticmethod
    def _is_free_key(event: QKeyEvent) -> bool:
        """Tell whether a key press is the one that is never captured.

        Args:
            event: The key event.

        Returns:
            True for Ctrl+Q.
        """
        return (
            event.key() == Qt.Key.Key_Q
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        )

    def _is_own_shortcut(self, event: QKeyEvent) -> bool:
        """Tell whether a key press is a shortcut of this editor.

        Args:
            event: The key event.

        Returns:
            True if an enabled action of the editor uses that shortcut.
        """
        pressed = QKeySequence(event.keyCombination())
        return any(
            action.isEnabled() and pressed in action.shortcuts()
            for action in self.actions()
        )

    def _install_event_filter(self):
        """Watch application events to capture keys and window closing."""
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Ask about unsaved changes on close and claim shortcuts.

        Closing: when the window that contains the editor is closed, the
        user is asked about unsaved changes, and the window stays open if
        they cancel. This works in any host window, with no extra code.

        Keys: Qt first offers every key to the shortcuts of the whole
        window. Accepting the ``ShortcutOverride`` event makes Qt deliver
        the key to the focused widget instead. Only widgets of this
        editor, in the same window, are affected; dialogs keep their own
        keys.

        Args:
            watched: The object that received the event.
            event: The event.

        Returns:
            True if the event was claimed, False to let it continue.
        """
        if (
            event.type() == QEvent.Type.Close
            and isinstance(watched, QWidget)
            and watched is self.window()
        ):
            if not self.maybe_save():
                event.ignore()
                return True
            return False

        if (
            self.capture_keys
            and event.type() == QEvent.Type.ShortcutOverride
            and isinstance(watched, QWidget)
            and watched.window() is self.window()
            and (watched is self or self.isAncestorOf(watched))
            and not self._is_free_key(event)
            and not self._is_own_shortcut(event)
        ):
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent):
        """Stop key presses that no inner widget used from going further.

        Args:
            event: The key event.
        """
        super().keyPressEvent(event)
        if self.capture_keys and not self._is_free_key(event):
            event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        """Stop key releases from reaching the host application.

        Args:
            event: The key event.
        """
        super().keyReleaseEvent(event)
        if self.capture_keys and not self._is_free_key(event):
            event.accept()

    def has_unsaved_changes(self) -> bool:
        """Tell whether the document differs from the last load or save.

        Returns:
            True if there are changes that were not saved.
        """
        return self.get_markdown_text() != self._saved_text

    def maybe_save(self) -> bool:
        """Ask what to do with unsaved changes before leaving the document.

        It runs automatically when the window is closed. A host can also
        call it before closing only the editor, for example a tab.

        Returns:
            True if it is safe to continue: there were no changes, they
            were saved, or the user chose to discard them. False if the
            user cancelled or the save failed.
        """
        if not self.has_unsaved_changes():
            return True

        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The document has unsaved changes.\n"
            "Do you want to save them before closing?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Save:
            return self.save_file()
        return answer == buttons.Discard


class MainWindow(QMainWindow):
    """Standalone application window hosting a ``MarkdownEditorWidget``."""

    def __init__(
        self,
        filepath: Optional[str] = None,
        template_text: Optional[str] = None,
        template_file: Optional[str] = None,
    ):
        """Create the window and load the given file, if any.

        Args:
            filepath: Optional path of a Markdown file to open.
            template_text: Optional template text, see
                ``MarkdownEditorWidget``.
            template_file: Optional template file, see
                ``MarkdownEditorWidget``.
        """
        super().__init__()
        self.setWindowTitle("Dual-Mode Markdown Editor (View / Edit)")
        self.resize(900, 650)

        self.markdown_editor = MarkdownEditorWidget(
            filepath=filepath,
            template_text=template_text,
            template_file=template_file,
            parent=self,
            auto_load=False,
        )
        self.setCentralWidget(self.markdown_editor)

        # Ctrl+Q is the one key the editor never captures. It closes the
        # window; the editor asks about unsaved changes before that.
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

        # Connect first so the "File loaded" message is not lost.
        self.markdown_editor.status_message.connect(
            self.statusBar().showMessage
        )
        self.markdown_editor.load_file()


def main(argv: Optional[List[str]] = None) -> int:
    """Run the editor as a standalone application.

    Args:
        argv: Command line arguments, ``sys.argv`` by default. The first
            argument after the program name is an optional Markdown file.

    Returns:
        The application exit code.
    """
    args = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(args)

    file_arg = args[1] if len(args) > 1 else None
    template_file = args[2] if len(args) > 2 else None

    window = MainWindow(file_arg, template_file=template_file)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
