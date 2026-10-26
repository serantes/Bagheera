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
import sys
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
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
    "main",
]

EDITOR_FONT_SIZE = 10
WEB_SCHEMES = ("http", "https", "mailto")
PROFILE_TEMPLATE = (
    ""
)


class DualModeMarkdownWidget(QTextBrowser):
    """Widget that toggles between rendered Markdown and plain text editing.

    In view mode the Markdown is rendered read-only and links are clickable.
    In edit mode the raw Markdown is shown with a strictly fixed monospace
    font and size, free of any formatting inherited from the rendered view.

    Attributes:
        raw_markdown: Last known Markdown source of the document.
        edit_mode: True while the widget is in plain text edit mode.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the widget in view mode.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.raw_markdown = ""
        self.edit_mode = False

        # Fonts are stored so each mode can restore its own appearance.
        self._view_font = QFont(self.font())
        self._edit_font = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        )
        self._edit_font.setPointSize(EDITOR_FONT_SIZE)

        # Links are handled manually in ``_on_anchor_clicked`` so that
        # local files never replace the document content.
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._on_anchor_clicked)

        self.set_view_mode()

    def get_markdown_text(self) -> str:
        """Return the current Markdown source, including unsaved edits.

        Returns:
            The Markdown text of the document.
        """
        if self.edit_mode:
            self.raw_markdown = self.toPlainText()
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
        """Deselect any selected text and remove focus from the widget."""
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.clearFocus()

    def set_view_mode(self):
        """Switch to the rendered Markdown view with clickable links."""
        if self.edit_mode:
            self.raw_markdown = self.toPlainText()

        self._release_selection_and_focus()

        self.edit_mode = False
        flags = Qt.TextInteractionFlag.TextBrowserInteraction
        self.setTextInteractionFlags(flags)

        # Restore the original font, since edit mode changed it.
        self.setFont(self._view_font)
        self.document().setDefaultFont(self._view_font)

        self.setMarkdown(self.raw_markdown)
        self.document().clearUndoRedoStacks()

    def set_edit_mode(self):
        """Switch to plain text editing with a fixed monospace font.

        Before switching, any selected text is deselected and the widget
        loses focus, which avoids rendering glitches from the view mode.
        """
        self._release_selection_and_focus()

        self.edit_mode = True
        flags = Qt.TextInteractionFlag.TextEditorInteraction
        self.setTextInteractionFlags(flags)

        self.setFont(self._edit_font)
        self.document().setDefaultFont(self._edit_font)

        # Load the raw content.
        self.setPlainText(self.raw_markdown)

        # Reset character formatting across the whole document to clear
        # any style or size inherited from the rendered view.
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)

        char_format = QTextCharFormat()
        char_format.setFont(self._edit_font)
        char_format.setFontPointSize(EDITOR_FONT_SIZE)
        cursor.mergeCharFormat(char_format)

        # Clear the selection and move the cursor to the start.
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        self.document().clearUndoRedoStacks()

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
        toolbar: The toolbar with the save and mode controls.
        save_action: The save action. A host that already uses Ctrl+S can
            free the shortcut with ``save_action.setShortcut(QKeySequence())``.
        filepath: Path of the current document, or None.
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
        """
        super().__init__(parent)
        self.filepath = filepath
        self.template_text = template_text
        self.template_file = template_file

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_area = DualModeMarkdownWidget()
        self.toolbar = self._create_toolbar()
        self.toolbar.setVisible(show_toolbar)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.text_area)

        if auto_load:
            self.load_file()

    def _create_toolbar(self) -> QToolBar:
        """Create the toolbar with save and mode toggle controls.

        Returns:
            The configured toolbar.
        """
        toolbar = QToolBar("Main Toolbar", self)

        self.save_action = QAction("💾 Save", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_file)
        toolbar.addAction(self.save_action)
        # Also register it on the widget so the shortcut keeps working
        # when the toolbar is hidden.
        self.addAction(self.save_action)

        toolbar.addSeparator()

        self.mode_btn = QPushButton("👁️ Switch to Edit Mode")
        self.mode_btn.setCheckable(True)
        self.mode_btn.clicked.connect(self.toggle_mode)
        toolbar.addWidget(self.mode_btn)
        return toolbar

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
        if is_editing:
            self.mode_btn.setText("📖 Switch to View Mode (Rendered)")
            self.status_message.emit("Edit mode activated (Plain text)", 2000)
        else:
            self.mode_btn.setText("👁️ Switch to Edit Mode")
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
            self.status_message.emit(f"File loaded: {self.filepath}", 4000)
            self.file_loaded.emit(self.filepath)
            return True

        self.set_markdown_text(self.get_template())
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

        try:
            with open(target, "w", encoding="utf-8") as file_obj:
                file_obj.write(self.get_markdown_text())
        except OSError as exception:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Could not write to the file:\n{exception}",
            )
            return False

        self.filepath = target
        self.status_message.emit(f"Changes saved to: {target}", 4000)
        self.file_saved.emit(target)
        return True


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
