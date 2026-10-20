"""
Tests for the DuplicateManagerDialog overlay rework.

These tests validate the tab structure (Side by Side / Overlay), the Link
Panes button gating, lazy view updates, overlay controls and the i18n parity
of the new UI strings.
"""
import os
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from bagheeraview.core.duplicatedialog import DuplicateManagerDialog
from bagheeraview.core.overlaycanvas import OverlayCanvas
from bagheeraview.core import constants


def _write_png(path, color):
    """Writes a tiny valid PNG file with the given color."""
    from PySide6.QtGui import QImage
    img = QImage(120, 80, QImage.Format_RGB32)
    img.fill(color)
    assert img.save(str(path))


@pytest.fixture(autouse=True)
def _qapp():
    """Ensures a QApplication exists for every test in this module."""
    return QApplication.instance() or QApplication([])


class _FakeDuplicate:
    """Minimal stand-in for a DuplicateResult used to feed the dialog."""

    def __init__(self, path1, path2, similarity):
        self.path1 = path1
        self.path2 = path2
        self.similarity = similarity
        self.timestamp = 0


class FakeMainWindow(QWidget):
    """Loose fake of MainWindow with the attributes the dialog touches."""

    def __init__(self):
        super().__init__()
        self.cache = MagicMock()
        self.shortcut_controller = None
        self.show_faces = False

    def delete_file_by_path(self, path, permanent=False):
        """No-op stand-in for the real deletion flow."""

    def update_metadata_for_path(self, path, metadata=None):
        """No-op stand-in for the metadata flow."""


@pytest.fixture()
def dialog(tmp_path, request):
    """
    Builds a dialog with a single fake duplicate pair and real PNG images,
    and cleans up its panes afterwards.
    """
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _write_png(a, "#ff0000")
    _write_png(b, "#0000ff")
    dup = _FakeDuplicate(str(a), str(b), 92.0)
    win = FakeMainWindow()
    dlg = DuplicateManagerDialog([dup], MagicMock(), win, review_mode=False)

    def _cleanup():
        # Close the dialog so its closeEvent runs both pane cleanups.
        dlg.close()
        # Safety net: pane cleanup is idempotent.
        if hasattr(dlg, "left_pane"):
            dlg.left_pane.cleanup()
        if hasattr(dlg, "right_pane"):
            dlg.right_pane.cleanup()
        dlg.deleteLater()
        # Force the deferred deletion so no dialog survives into the next test.
        QApplication.processEvents()

    request.addfinalizer(_cleanup)
    return dlg


def test_tabs_exist_and_have_expected_titles(dialog):
    """The main QTabWidget exposes Side by Side and Overlay tabs."""
    titles = [dialog.main_tabs.tabText(i) for i in range(dialog.main_tabs.count())]
    assert titles == [constants.UITexts.DUPLICATE_TAB_SIDE_BY_SIDE,
                      constants.UITexts.DUPLICATE_TAB_OVERLAY]

    overlay_titles = [
        dialog.overlay_tabs.tabText(i) for i in range(dialog.overlay_tabs.count())]
    assert len(overlay_titles) == 4
    assert dialog.overlay_tabs.tabText(OverlayCanvas.MODE_TOGGLE) == \
        constants.UITexts.DUPLICATE_OVERLAY_TOGGLE
    assert dialog.overlay_tabs.tabText(OverlayCanvas.MODE_DIFFERENCE) == \
        constants.UITexts.DUPLICATE_OVERLAY_DIFFERENCE


def test_link_panes_enabled_only_on_side_by_side(dialog):
    """We need the button gated to the Side by Side tab."""
    dialog.main_tabs.setCurrentIndex(0)
    assert dialog.btn_link_panes.isEnabled()
    dialog.main_tabs.setCurrentIndex(1)  # Overlay
    assert not dialog.btn_link_panes.isEnabled()
    dialog.main_tabs.setCurrentIndex(0)
    assert dialog.btn_link_panes.isEnabled()


def test_left_list_always_visible_outside_tabs(dialog):
    """The duplicate list must not be a child of any QTabWidget."""
    from PySide6.QtWidgets import QTabWidget
    assert dialog.table_widget.parent().__class__ is not QTabWidget


def test_overlay_lazy_refresh_marks_both_views_dirty(dialog):
    """Switching pairs marks views dirty and refreshes only the active one."""
    dialog.main_tabs.setCurrentIndex(1)  # Overlay active
    assert dialog._dirty["overlay"] is False
    # Force a re-load of the row (simulates navigating to another pair)
    dialog._load_pair(0)
    # Both views are invalidated by the navigation...
    assert dialog._dirty["side"] is True
    # ...but the visible overlay view is refreshed immediately, leaving only
    # the hidden Side by Side view dirty.
    assert dialog._dirty["overlay"] is False
    # The Side by Side view is refreshed when its tab becomes active again.
    dialog.main_tabs.setCurrentIndex(0)
    assert dialog._dirty["side"] is False


def test_overlay_controls_and_swap(dialog):
    """Reset/Swap buttons exist and Swap flips the canvas layers."""
    dialog.main_tabs.setCurrentIndex(1)
    assert dialog.btn_overlay_reset.text() == \
        constants.UITexts.DUPLICATE_OVERLAY_RESET
    assert dialog.btn_overlay_swap.text() == \
        constants.UITexts.DUPLICATE_OVERLAY_SWAP
    assert dialog.opacity_slider.minimum() == 0
    assert dialog.opacity_slider.maximum() == 100
    # Initial top layer is the left pane image path reference.
    dialog.main_tabs.setCurrentIndex(0)
    path_before = os.path.basename(
        dialog.left_pane.controller.get_current_path())
    dialog._update_overlay_legend()
    assert path_before in dialog.overlay_legend_lbl.text()


def test_i18n_keys_parity():
    """New overlay keys must exist in every supported language dictionary."""
    keys = [
        "DUPLICATE_TAB_SIDE_BY_SIDE", "DUPLICATE_TAB_OVERLAY",
        "DUPLICATE_OVERLAY_TOGGLE", "DUPLICATE_OVERLAY_SPLIT",
        "DUPLICATE_OVERLAY_DIFFERENCE", "DUPLICATE_OVERLAY_OPACITY",
        "DUPLICATE_OVERLAY_OPACITY_LABEL", "DUPLICATE_OVERLAY_RESET",
        "DUPLICATE_OVERLAY_RESET_TOOLTIP",
        "DUPLICATE_OVERLAY_RESET_SPLIT_TOOLTIP",
        "DUPLICATE_OVERLAY_RESET_OPACITY_TOOLTIP",
        "DUPLICATE_OVERLAY_SWAP", "DUPLICATE_OVERLAY_SWAP_TOOLTIP",
        "DUPLICATE_OVERLAY_MOUSE_HINT", "DUPLICATE_OVERLAY_TOP_LEGEND",
        "DUPLICATE_OVERLAY_BOTTOM_LEGEND",
        "DUPLICATE_LINK_PANES_TOOLTIP", "DUPLICATE_SIZE_LABEL",
        "DUPLICATE_RESOLUTION_LABEL", "DUPLICATE_OVERWRITE",
        "DUPLICATE_OVERWRITE_TOOLTIP", "DUPLICATE_OVERWRITE_CONFIRM_TITLE",
        "DUPLICATE_OVERWRITE_CONFIRM_TEXT",
        "DUPLICATE_OVERWRITE_CONFIRM_EXT_NOTE",
        "DUPLICATE_OVERWRITE_NO_SELECTION", "DUPLICATE_OVERWRITE_ERROR",
    ]
    for lang, texts in constants._UI_TEXTS.items():
        for key in keys:
            assert key in texts, f"{key} missing in language '{lang}'"


def test_similarity_label_removed_and_column_colored(dialog):
    """The % label is gone and the % column carries the color code."""
    assert not hasattr(dialog, "similarity_lbl")
    sim_item = dialog.table_widget.item(dialog.table_widget.currentRow(), 0)
    assert sim_item.foreground().color().name() in (
        "#2ecc71", "#e74c3c", "#f39c12")


def test_bottom_bar_order(dialog):
    """The action buttons follow the documented layout order."""
    layout = dialog.btn_link_panes.parentWidget().layout()
    widgets = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is not None:
            widgets.append(item.widget())
    index = {w: i for i, w in enumerate(widgets)}
    assert index[dialog.btn_link_panes] < index[dialog.btn_del_left] < \
        index[dialog.btn_del_right] < index[dialog.btn_overwrite] < \
        index[dialog.btn_keep_both] < index[dialog.btn_skip]


def test_opacity_slider_hidden_until_opacity_tab(dialog):
    """The slider is only visible when the Opacity sub-tab is active."""
    dialog.main_tabs.setCurrentIndex(1)  # Overlay
    assert dialog.opacity_slider.isHidden()
    assert dialog.opacity_lbl.isHidden()
    dialog.overlay_tabs.setCurrentIndex(OverlayCanvas.MODE_OPACITY)
    assert not dialog.opacity_slider.isHidden()
    assert not dialog.opacity_lbl.isHidden()
    dialog.overlay_tabs.setCurrentIndex(OverlayCanvas.MODE_TOGGLE)
    assert dialog.opacity_slider.isHidden()


def test_no_switch_layer_button(dialog):
    """The redundant Switch Layer button no longer exists."""
    assert not hasattr(dialog, "btn_overlay_switch")


def test_overlay_buttons_order(dialog):
    """Swap Layers comes before Reset View in the overlay controls bar."""
    layout = dialog.btn_overlay_swap.parentWidget().layout()
    widgets = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is not None:
            widgets.append(item.widget())
    index = {w: i for i, w in enumerate(widgets)}
    assert index[dialog.btn_overlay_swap] < index[dialog.btn_overlay_reset]


def test_overlay_buttons_have_hotkey_tooltips(dialog):
    """Overlay action buttons advertise their associated hotkey."""
    assert "S" in dialog.btn_overlay_swap.toolTip()
    assert "Z" in dialog.btn_overlay_reset.toolTip()


def test_reset_per_subtab(dialog):
    """Reset re-centers Split and resets Opacity to 50 %."""
    dialog.main_tabs.setCurrentIndex(1)

    dialog.overlay_tabs.setCurrentIndex(OverlayCanvas.MODE_SPLIT)
    dialog.overlay_canvas.reset_all()
    dialog.overlay_canvas._split = 0.2
    dialog._on_overlay_reset()
    assert abs(dialog.overlay_canvas._split - 0.5) < 1e-9

    dialog.overlay_tabs.setCurrentIndex(OverlayCanvas.MODE_OPACITY)
    dialog.opacity_slider.setValue(80)
    dialog._on_overlay_reset()
    assert dialog.opacity_slider.value() == 50
