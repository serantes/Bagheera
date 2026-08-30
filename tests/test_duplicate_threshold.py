import os
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
from bagheeraview.core.duplicatecache import DuplicateCache, DuplicateDetector
from bagheeraview.core.settings import SettingsDialog


def get_qapp():
    return QApplication.instance() or QApplication([])


def test_duplicate_cache_clear_pending(tmp_path):
    get_qapp()
    db_dir = tmp_path / "test_dup_db"
    os.makedirs(db_dir, exist_ok=True)

    file1 = tmp_path / "file1.png"
    file2 = tmp_path / "file2.png"
    file1.write_text("dummy 1")
    file2.write_text("dummy 2")

    path1 = str(file1)
    path2 = str(file2)

    with patch("bagheeraview.core.duplicatecache.DUPLICATE_CACHE_PATH", str(db_dir)):
        cache = DuplicateCache()
        # Add a pending entry
        cache.mark_as_pending(path1, path2, is_pending=True, similarity=90)
        pending_before = cache.get_all_pending_duplicates()
        assert len(pending_before) == 1

        # Clear pending search cache
        res = cache.clear_pending()
        assert res is True

        pending_after = cache.get_all_pending_duplicates()
        assert len(pending_after) == 0
        cache.lmdb_close()


def test_settings_dialog_threshold_cancel(qtbot):
    get_qapp()
    parent_widget = QWidget()
    parent_widget.duplicate_cache = MagicMock()

    dlg = SettingsDialog(parent_widget)
    try:
        dlg.load_settings()

        initial_val = dlg.duplicate_threshold_slider.value()
        new_val = initial_val + 5 if initial_val <= 95 else initial_val - 5

        # Mock QMessageBox.exec to return No (Cancel)
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.No):
            dlg.duplicate_threshold_slider.setValue(new_val)
            dlg._on_duplicate_threshold_released()

        # Should be reverted to initial value
        assert dlg.duplicate_threshold_slider.value() == initial_val
        assert dlg._clear_search_cache_on_save is False
    finally:
        dlg.close()


def test_settings_dialog_threshold_confirm_and_save(qtbot):
    get_qapp()
    parent_widget = QWidget()
    parent_widget.duplicate_cache = MagicMock()

    dlg = SettingsDialog(parent_widget)
    try:
        dlg.load_settings()

        initial_val = dlg.duplicate_threshold_slider.value()
        new_val = initial_val + 5 if initial_val <= 95 else initial_val - 5

        # Mock QMessageBox.exec to return Yes (Confirm)
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.Yes):
            dlg.duplicate_threshold_slider.setValue(new_val)
            dlg._on_duplicate_threshold_released()

        # Should keep new value and mark cache to clear on save
        assert dlg.duplicate_threshold_slider.value() == new_val
        assert dlg._clear_search_cache_on_save is True

        with patch("bagheeraview.core.settings.save_app_config"):
            dlg.accept()

        parent_widget.duplicate_cache.clear_pending.assert_called_once()
    finally:
        dlg.close()


def test_duplicate_detector_remembers_zero_duplicates_for_same_threshold(tmp_path):
    get_qapp()
    db_dir = tmp_path / "test_dup_db"
    os.makedirs(db_dir, exist_ok=True)

    file1 = tmp_path / "file1.png"
    file2 = tmp_path / "file2.png"
    file1.write_text("dummy 1")
    file2.write_text("dummy 2")

    path1 = str(file1)
    path2 = str(file2)

    with patch("bagheeraview.core.duplicatecache.DUPLICATE_CACHE_PATH", str(db_dir)):
        cache = DuplicateCache()

        mtime1 = os.stat(path1).st_mtime
        mtime2 = os.stat(path2).st_mtime

        # Add pre-computed different hashes to cache (distance > threshold)
        h_dummy1 = "0000000000000000"
        h_dummy2 = "ffffffffffffffff"
        cache.add_hash_for_path(path1, h_dummy1, mtime1)
        cache.add_hash_for_path(path2, h_dummy2, mtime2)

        # Run detector 1st time (threshold 90) -> 0 duplicates found
        pool_manager = MagicMock()
        detector1 = DuplicateDetector(
            [path1, path2], cache, pool_manager,
            method="histogram_hashing", threshold=90, force_full=False
        )
        results1 = []
        detector1.duplicates_found.connect(lambda res: results1.extend(res))
        detector1.run()
        assert len(results1) == 0
        assert cache.is_pending_scan_completed(90) is True

        # Run detector 2nd time (same threshold 90) -> Should rely on completed scan metadata and early exit
        detector2 = DuplicateDetector(
            [path1, path2], cache, pool_manager,
            method="histogram_hashing", threshold=90, force_full=False
        )
        results2 = []
        detector2.duplicates_found.connect(lambda res: results2.extend(res))
        
        with patch.object(cache, "persistent_bktree_query") as mock_query:
            detector2.run()
            # persistent_bktree_query should NOT be called because early exit triggered
            mock_query.assert_not_called()

        assert len(results2) == 0
        cache.lmdb_close()


def test_duplicate_detector_reanalyzes_when_threshold_changed(tmp_path):
    get_qapp()
    db_dir = tmp_path / "test_dup_db"
    os.makedirs(db_dir, exist_ok=True)

    file1 = tmp_path / "file1.png"
    file2 = tmp_path / "file2.png"
    file1.write_text("dummy 1")
    file2.write_text("dummy 2")

    path1 = str(file1)
    path2 = str(file2)

    with patch("bagheeraview.core.duplicatecache.DUPLICATE_CACHE_PATH", str(db_dir)):
        cache = DuplicateCache()

        mtime1 = os.stat(path1).st_mtime
        mtime2 = os.stat(path2).st_mtime

        # Add pre-computed identical hashes
        h_dummy = "1234567890abcdef"
        cache.add_hash_for_path(path1, h_dummy, mtime1)
        cache.add_hash_for_path(path2, h_dummy, mtime2)

        # Run detector at threshold 95
        detector1 = DuplicateDetector(
            [path1, path2], cache, MagicMock(),
            method="histogram_hashing", threshold=95, force_full=False
        )
        detector1.run()
        assert cache.is_pending_scan_completed(95) is True

        # Clear pending cache (simulating saving settings with new threshold 70)
        cache.clear_pending()

        # is_pending_scan_completed for new threshold 70 should now be False
        assert cache.is_pending_scan_completed(70) is False

        # Run detector at new threshold 70 -> Should re-analyze
        detector2 = DuplicateDetector(
            [path1, path2], cache, MagicMock(),
            method="histogram_hashing", threshold=70, force_full=False
        )
        results2 = []
        detector2.duplicates_found.connect(lambda res: results2.extend(res))
        detector2.run()

        assert len(results2) == 1
        assert cache.is_pending_scan_completed(70) is True
        cache.lmdb_close()
