"""Dialogs for editing tag information stored in LMDB."""

from urllib.parse import quote_plus

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QMenu,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QStyle,
)

from .constants import UITexts
from .md_editor import MarkdownEditorWidget


class TagInfoSearchDialog(QDialog):
    """Filter and select a tag that already has information."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(UITexts.TAG_INFO_FIND)
        self.resize(450, 500)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(UITexts.TAG_INFO_SELECT_TAG, self))
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText(UITexts.TAG_INFO_FILTER)
        layout.addWidget(self.filter_edit)
        self.tag_list = QListWidget(self)
        layout.addWidget(self.tag_list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            UITexts.TAG_INFO_SELECT
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            UITexts.CANCEL
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.filter_edit.textChanged.connect(self._refresh_tags)
        self.tag_list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.tag_list.currentRowChanged.connect(
            lambda row: buttons.button(
                QDialogButtonBox.StandardButton.Ok
            ).setEnabled(row >= 0)
        )
        self.select_button = buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )
        self._refresh_tags()

    def _refresh_tags(self):
        current = self.selected_tag()
        self.tag_list.clear()
        self.tag_list.addItems(
            self.store.tags_with_info(self.filter_edit.text())
        )
        if current:
            matches = self.tag_list.findItems(
                current, Qt.MatchFlag.MatchExactly
            )
            if matches:
                self.tag_list.setCurrentItem(matches[0])
        elif self.tag_list.count():
            self.tag_list.setCurrentRow(0)
        self.select_button.setEnabled(self.tag_list.currentRow() >= 0)

    def selected_tag(self):
        item = self.tag_list.currentItem()
        return item.text() if item else None


class TemplateNameDialog(QDialog):
    """Choose an existing template or enter a new template name."""

    def __init__(self, names, parent=None):
        super().__init__(parent)
        self.setWindowTitle(UITexts.TAG_INFO_SAVE_AS_TEMPLATE)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(UITexts.TAG_INFO_TEMPLATE_NAME, self))
        self.name_combo = QComboBox(self)
        self.name_combo.setEditable(True)
        self.name_combo.addItems(names)
        layout.addWidget(self.name_combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            UITexts.TAG_INFO_SAVE
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            UITexts.CANCEL
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def template_name(self):
        return self.name_combo.currentText().strip()


class TagInformationEditor(QDialog):
    """Edit one tag's Markdown information and manage shared references."""

    information_changed = Signal(str, bool)

    def __init__(self, tag, store, parent=None):
        super().__init__(parent)
        self.tag = tag
        self.store = store
        self.setWindowTitle(UITexts.TAG_INFO_TITLE.format(tag))
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar = QToolBar(self)
        layout.addWidget(self.toolbar)

        self.editor = MarkdownEditorWidget(
            template_text=store.get_info(tag) or "",
            parent=self,
            show_toolbar=True,
            auto_load=True,
            capture_keys=True,
            tag=tag,
            split_toolbars=True,
            confirm_close=False,
        )
        self.editor.toolbar.hide()
        layout.addWidget(self.editor, stretch=1)
        self._saved_text = self.editor.get_markdown_text()
        self.editor.save_action.triggered.disconnect()
        self.editor.save_action.triggered.connect(
            lambda _checked=False: self._save_tag_info()
        )

        self._create_actions()
        self._refresh_menus()

    def _create_actions(self):
        self.new_action = QAction(UITexts.TAG_INFO_NEW, self)
        self.new_action.setIcon(self._icon(
            "document-new", QStyle.StandardPixmap.SP_FileIcon
        ))
        self.new_action.triggered.connect(self._new_document)
        self.new_button = self._button(self.new_action)
        self.new_button.setMenu(self._new_menu())
        self.toolbar.addWidget(self.new_button)

        self.save_action = QAction(UITexts.TAG_INFO_SAVE, self)
        self.save_action.setIcon(self._icon(
            "document-save", QStyle.StandardPixmap.SP_DialogSaveButton
        ))
        self.save_action.triggered.connect(self._save_tag_info)
        self.save_button = self._button(self.save_action)
        self.save_menu = QMenu(self.save_button)
        self.save_button.setMenu(self.save_menu)
        self.save_menu.addAction(
            UITexts.TAG_INFO_SAVE_AS_TEMPLATE,
            self._save_as_template,
        )
        self.toolbar.addWidget(self.save_button)

        self.delete_action = QAction(UITexts.TAG_INFO_DELETE, self)
        self.delete_action.setIcon(self._icon(
            "edit-delete", QStyle.StandardPixmap.SP_TrashIcon
        ))
        self.delete_action.triggered.connect(self._delete_tag_info)
        self.delete_button = self._button(self.delete_action)
        self.delete_button.setMenu(self._delete_menu())
        self.toolbar.addWidget(self.delete_button)

        self.search_action = QAction(UITexts.TAG_INFO_FIND, self)
        self.search_action.setIcon(self._icon(
            "edit-find", QStyle.StandardPixmap.SP_FileDialogContentsView
        ))
        self.search_action.triggered.connect(self._find_tag)
        self.toolbar.addAction(self.search_action)
        self.toolbar.addSeparator()

        self.edit_action = QAction(UITexts.TAG_INFO_EDIT, self)
        self.edit_action.setIcon(self._icon(
            "document-edit", QStyle.StandardPixmap.SP_FileDialogDetailedView
        ))
        self.edit_action.setToolTip(UITexts.TAG_INFO_EDIT)
        self.edit_action.setCheckable(True)
        self.edit_action.triggered.connect(
            lambda _checked=False: self.editor.toggle_mode()
        )
        self.editor.mode_changed.connect(self.edit_action.setChecked)
        self.toolbar.addAction(self.edit_action)
        self.toolbar.addSeparator()

        self.web_search_action = QAction(UITexts.TAG_INFO_WEB_SEARCH, self)
        self.web_search_action.triggered.connect(
            lambda _checked=False: self._search_web("DuckDuckGo")
        )
        self.web_search_button = self._button(self.web_search_action)
        self.web_search_button.setMenu(self._web_search_menu())
        self.toolbar.addWidget(self.web_search_button)
        self.toolbar.addAction(self.editor.wikipedia_action)

    @staticmethod
    def _icon(theme_name, fallback):
        return QIcon.fromTheme(
            theme_name, QApplication.style().standardIcon(fallback)
        )

    def _button(self, action):
        button = QToolButton(self.toolbar)
        button.setDefaultAction(action)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        return button

    def _new_menu(self):
        menu = QMenu(self.new_button)
        menu.aboutToShow.connect(
            lambda: self._populate_template_menu(menu, self._load_template)
        )
        return menu

    def _delete_menu(self):
        menu = QMenu(self.delete_button)
        menu.aboutToShow.connect(
            lambda: self._populate_template_menu(menu, self._delete_template)
        )
        return menu

    def _populate_template_menu(self, menu, callback):
        menu.clear()
        templates = self.store.templates()
        if not templates:
            action = menu.addAction(UITexts.TAG_INFO_NO_TEMPLATES)
            action.setEnabled(False)
            return
        if callback == self._delete_template:
            title = menu.addAction(UITexts.TAG_INFO_DELETE_TEMPLATE)
            title.setEnabled(False)
            menu.addSeparator()
        for name in templates:
            action = menu.addAction(name)
            action.triggered.connect(
                lambda _checked=False, template=name: callback(template)
            )

    def _refresh_menus(self):
        self.new_button.setToolTip(UITexts.TAG_INFO_NEW)
        self.save_button.setToolTip(UITexts.TAG_INFO_SAVE)
        self.delete_button.setToolTip(UITexts.TAG_INFO_DELETE)
        self.search_action.setToolTip(UITexts.TAG_INFO_FIND)
        self.web_search_action.setToolTip(UITexts.TAG_INFO_WEB_SEARCH)

    def _web_search_menu(self):
        menu = QMenu(self.web_search_button)
        for engine in ("DuckDuckGo", "Google", "Bing", "Yahoo", "Brave", "Ecosia"):
            action = menu.addAction(engine)
            action.triggered.connect(
                lambda _checked=False, name=engine: self._search_web(name)
            )
        return menu

    def _new_document(self):
        self.editor.set_markdown_text("")

    def _load_template(self, name):
        markdown = self.store.get_template(name)
        if markdown is not None:
            self.editor.set_markdown_text(markdown)

    def _save_tag_info(self):
        try:
            self.store.save_info(self.tag, self.editor.get_markdown_text())
        except Exception as exc:
            self._show_error(exc)
            return
        self._saved_text = self.editor.get_markdown_text()
        self.information_changed.emit(self.tag, True)

    def _save_as_template(self):
        dialog = TemplateNameDialog(self.store.templates(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.template_name()
        if not name:
            QMessageBox.warning(
                self, UITexts.TAG_INFO_SAVE_AS_TEMPLATE,
                UITexts.TAG_INFO_TEMPLATE_NAME_REQUIRED
            )
            return
        if name in self.store.templates():
            if not self._confirm(
                UITexts.TAG_INFO_SAVE_AS_TEMPLATE,
                UITexts.TAG_INFO_CONFIRM_OVERWRITE_TEMPLATE.format(name),
            ):
                return
        try:
            self.store.save_template(name, self.editor.get_markdown_text())
        except Exception as exc:
            self._show_error(exc)

    def _delete_tag_info(self):
        if not self.store.has_info(self.tag):
            return
        if not self._confirm(
            UITexts.TAG_INFO_DELETE,
            UITexts.TAG_INFO_CONFIRM_DELETE_TAG.format(self.tag),
        ):
            return
        try:
            self.store.delete_tag(self.tag)
        except Exception as exc:
            self._show_error(exc)
            return
        self.editor.set_markdown_text("")
        self._saved_text = ""
        self.information_changed.emit(self.tag, False)

    def _delete_template(self, name):
        if self._confirm(
            UITexts.TAG_INFO_DELETE_TEMPLATE,
            UITexts.TAG_INFO_CONFIRM_DELETE_TEMPLATE.format(name),
        ):
            try:
                self.store.delete_template(name)
            except Exception as exc:
                self._show_error(exc)

    def _find_tag(self):
        dialog = TagInfoSearchDialog(self.store, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source_tag = dialog.selected_tag()
        if not source_tag or source_tag == self.tag:
            return
        if not self._resolve_unsaved_changes():
            return
        if (
            self.store.has_info(self.tag)
            and self.store.get_info_key(self.tag)
            != self.store.get_info_key(source_tag)
        ):
            if not self._confirm(
                UITexts.TAG_INFO_FIND,
                UITexts.TAG_INFO_CONFIRM_REASSOCIATE.format(self.tag),
            ):
                return
        try:
            self.store.associate(self.tag, source_tag)
            self.editor.set_markdown_text(
                self.store.get_info(self.tag) or ""
            )
        except Exception as exc:
            self._show_error(exc)
            return
        self._saved_text = self.editor.get_markdown_text()
        self.information_changed.emit(self.tag, True)

    def _resolve_unsaved_changes(self):
        text = self.editor.get_markdown_text()
        if text == self._saved_text:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(UITexts.TAG_INFO_FIND)
        box.setText(UITexts.TAG_INFO_UNSAVED_CHANGES)
        save_button = box.addButton(
            UITexts.TAG_INFO_SAVE, QMessageBox.ButtonRole.AcceptRole
        )
        discard_button = box.addButton(
            UITexts.TAG_INFO_DISCARD, QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(UITexts.CANCEL, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_button:
            self._save_tag_info()
            return self.editor.get_markdown_text() == self._saved_text
        return clicked is discard_button

    def _search_web(self, engine="DuckDuckGo"):
        query = self.tag.rsplit("/", 1)[-1]
        encoded_query = quote_plus(query)
        search_urls = {
            "DuckDuckGo": f"https://duckduckgo.com/?q={encoded_query}",
            "Google": f"https://www.google.com/search?q={encoded_query}",
            "Bing": f"https://www.bing.com/search?q={encoded_query}",
            "Yahoo": f"https://search.yahoo.com/search?p={encoded_query}",
            "Brave": f"https://search.brave.com/search?q={encoded_query}",
            "Ecosia": f"https://www.ecosia.org/search?q={encoded_query}",
        }
        try:
            url = QUrl(search_urls[engine])
        except KeyError:
            raise ValueError(f"Unsupported web search engine: {engine}") from None
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self, UITexts.ERROR, UITexts.TAG_INFO_BROWSER_ERROR
            )

    def _confirm(self, title, text):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        yes_button = box.addButton(
            UITexts.TAG_INFO_YES, QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(UITexts.TAG_INFO_NO, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(box.buttons()[-1])
        box.exec()
        return box.clickedButton() is yes_button

    def _show_error(self, error):
        QMessageBox.critical(self, UITexts.ERROR, str(error))

    def closeEvent(self, event):
        if self.editor.get_markdown_text() != self._saved_text:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(UITexts.TAG_INFO_TITLE.format(self.tag))
            box.setText(UITexts.TAG_INFO_CONFIRM_CLOSE)
            save_button = box.addButton(
                UITexts.TAG_INFO_SAVE, QMessageBox.ButtonRole.AcceptRole
            )
            discard_button = box.addButton(
                UITexts.TAG_INFO_DISCARD,
                QMessageBox.ButtonRole.DestructiveRole,
            )
            box.addButton(UITexts.CANCEL, QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(save_button)
            box.exec()
            clicked = box.clickedButton()
            if clicked is save_button:
                self._save_tag_info()
                if self.editor.get_markdown_text() == self._saved_text:
                    event.accept()
                    return
            elif clicked is discard_button:
                event.accept()
                return
            event.ignore()
            return
        event.accept()
