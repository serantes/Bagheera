import pytest
from PySide6.QtWidgets import QApplication

from bagheeraview.core.app import MainWindow
from bagheeraview.core.constants import APP_CONFIG, IMAGE_EXTENSIONS
from bagheeraview.core.faiss_worker import FAISSSimilarSearchWorker
from bagheeraview.core.settings import DuplicateFileCounter, SettingsDialog


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("scan_dirs", [False, True])
@pytest.mark.parametrize("scan_files", [False, True])
def test_whitelist_scans_respect_hidden_settings(
        qapp, tmp_path, monkeypatch, scan_dirs, scan_files):
    root = tmp_path / "visible"
    explicit = tmp_path / ".explicit"
    paths = [
        root / "image.jpg",
        root / ".image.jpg",
        root / ".hidden" / "nested.jpg",
        root / ".hidden" / ".nested.jpg",
        root / "blocked" / "excluded.jpg",
        explicit / "included.jpg",
        explicit / ".included.jpg",
        explicit / ".nested" / "nested.jpg",
        explicit / "blocked" / "excluded.jpg",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    whitelist = [str(root), str(explicit)]
    blacklist = {str(root / "blocked"), str(explicit / "blocked")}
    monkeypatch.setitem(APP_CONFIG, "duplicate_whitelist", ",".join(whitelist))
    monkeypatch.setitem(APP_CONFIG, "duplicate_blacklist", ",".join(blacklist))
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_dirs", scan_dirs)
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_files", scan_files)

    expected = {str(paths[0]), str(paths[5])}
    if scan_files:
        expected.update((str(paths[1]), str(paths[6])))
    if scan_dirs:
        expected.update((str(paths[2]), str(paths[7])))
        if scan_files:
            expected.add(str(paths[3]))

    gathered = MainWindow._gather_files_for_duplicates(None)
    counter = DuplicateFileCounter(
        whitelist, blacklist, IMAGE_EXTENSIONS, scan_dirs, scan_files)
    counts = []
    counter.finished.connect(counts.append)
    counter.run()
    worker = FAISSSimilarSearchWorker(
        str(paths[0]), 80, ",".join(whitelist), ",".join(blacklist))

    assert set(gathered) == expected
    assert counts == [len(expected)]
    assert set(worker._get_all_images()) == expected


def test_similar_search_visible_paths_remain_explicit(qapp, tmp_path, monkeypatch):
    hidden = tmp_path / ".hidden.jpg"
    hidden.touch()
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_files", False)
    worker = FAISSSimilarSearchWorker(
        str(hidden), 80, str(tmp_path), "", visible_paths=[str(hidden)])

    assert worker._get_all_images() == [str(hidden)]


def test_hidden_directory_explicitly_whitelisted_below_visible_root(
        qapp, tmp_path, monkeypatch):
    root = tmp_path / "root"
    hidden = root / ".hidden"
    nested = hidden / ".nested"
    nested.mkdir(parents=True)
    image = hidden / "included.jpg"
    image.touch()
    (nested / "excluded.jpg").touch()
    whitelist = [str(root), str(hidden)]
    monkeypatch.setitem(APP_CONFIG, "duplicate_whitelist", ",".join(whitelist))
    monkeypatch.setitem(APP_CONFIG, "duplicate_blacklist", "")
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_dirs", False)
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_files", False)

    assert MainWindow._gather_files_for_duplicates(None) == [str(image)]
    worker = FAISSSimilarSearchWorker(
        str(image), 80, ",".join(whitelist), "")
    assert worker._get_all_images() == [str(image)]


@pytest.mark.parametrize("scan_files", [False, True])
def test_similar_search_hidden_file_whitelist_obeys_file_setting(
        qapp, tmp_path, monkeypatch, scan_files):
    hidden = tmp_path / ".hidden.jpg"
    hidden.touch()
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_files", scan_files)
    worker = FAISSSimilarSearchWorker(str(hidden), 80, str(hidden), "")

    assert worker._get_all_images() == ([str(hidden)] if scan_files else [])


def test_settings_count_uses_unsaved_hidden_options(qapp, tmp_path, monkeypatch):
    (tmp_path / "visible.jpg").touch()
    (tmp_path / ".hidden.jpg").touch()
    monkeypatch.setitem(APP_CONFIG, "duplicate_whitelist", str(tmp_path))
    monkeypatch.setitem(APP_CONFIG, "duplicate_blacklist", "")
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_dirs", False)
    monkeypatch.setitem(APP_CONFIG, "scan_hidden_files", False)
    dialog = SettingsDialog()
    try:
        dialog.scan_hidden_files_checkbox.setChecked(True)
        assert dialog.count_update_timer.isActive()
        dialog.update_duplicate_scan_count()
        dialog.counter_thread.wait()
        counts = []
        dialog.counter_thread.finished.connect(counts.append)
        dialog.counter_thread.run()
        assert counts == [2]
        assert APP_CONFIG["scan_hidden_files"] is False
        dialog.count_update_timer.stop()
        dialog.scan_hidden_dirs_checkbox.setChecked(True)
        assert dialog.count_update_timer.isActive()
    finally:
        dialog.count_update_timer.stop()
        dialog._stop_counter_thread()
        dialog.close()
