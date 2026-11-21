import json
import os
import struct
import threading
import time
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import app, filesystemwatcher, imagescanner, metadatamanager
from bagheeraview.core.constants import (
    APP_CONFIG, IMAGE_DATA_ROLE, ITEM_TYPE_ROLE, UITexts,
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_generator_replaces_priority_without_losing_background_work():
    generator = imagescanner.ThumbnailGenerator(
        None, ["a", "b", "c", "d", "e"], 128, None)

    generator.prioritize(["c", "d", "c"])
    assert generator._take_batch(1) == ["c"]
    generator.prioritize(["e"])
    assert generator._take_batch(2) == ["e", "a"]
    assert generator._take_batch(3) == ["b", "d"]
    assert generator._take_batch(1) == []


def test_generator_can_requeue_a_changed_inflight_image():
    generator = imagescanner.ThumbnailGenerator(
        None, ["a", "b"], 128, None)

    assert generator._take_batch(1) == ["a"]
    assert generator.add_paths(["a", "c"])
    generator.prioritize(["a", "c"])
    assert generator._take_batch(3) == ["a", "c", "b"]
    assert generator._take_batch(1) == []
    assert not generator.add_paths(["d"])


def test_changed_image_is_queued_without_discarding_background_work():
    generator = Mock(size=128)
    generator.isRunning.return_value = True
    generator.add_paths.return_value = True
    window = SimpleNamespace(
        _is_loading=False, current_thumb_size=128,
        _get_tier_for_size=lambda size: size,
        thumbnail_generator=generator,
        _priority_thumbnail_paths=lambda: ["visible"],
        generate_missing_thumbnails=Mock())

    app.MainWindow._queue_thumbnail_refresh(window, "changed")

    generator.add_paths.assert_called_once_with(["changed"])
    generator.prioritize.assert_called_once_with(["changed", "visible"])
    window.generate_missing_thumbnails.assert_not_called()


def test_regeneration_restarts_active_background_work_after_invalidation(qapp):
    events = []
    generator = Mock(force_thumbnail_refresh=False)
    generator.isRunning.return_value = True
    generator.stop.side_effect = lambda: events.append("stop")
    cache = Mock()
    cache.invalidate_path.side_effect = lambda path: events.append(("invalidate", path))
    restarted = Mock()
    window = SimpleNamespace(
        thumbnail_generator=generator, _thumbnail_generation=0, cache=cache,
        found_items_data=[("changed", None), ("other", None)],
        _model_update_queue=deque(), _path_to_model_index={},
        thumbnail_view=Mock(), current_thumb_size=128,
        _get_tier_for_size=lambda size: size,
        get_all_image_paths=lambda: ["changed", "other"],
        _priority_thumbnail_paths=lambda: ["other"])

    def start(paths, size, force_thumbnail_refresh=False):
        events.append(("start", paths, size, force_thumbnail_refresh))
        window.thumbnail_generator = restarted

    window._start_thumbnail_generator = start
    app.MainWindow.regenerate_thumbnail(window, "changed")

    assert events == [
        "stop", ("invalidate", "changed"),
        ("start", ["changed", "other"], 128, False),
    ]
    restarted.prioritize.assert_called_once_with(["changed", "other"])
    assert isinstance(window._model_update_queue, deque)


def test_metadata_only_batches_are_cached(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    path = tmp_path / "image.png"
    path.touch()
    stat = path.stat()
    cache = imagescanner.ThumbnailCache()
    try:
        cache._batch_write_to_lmdb([
            (stat.st_dev, struct.pack("Q", stat.st_ino), None, stat.st_mtime,
             -1, None, (["Person/Ada"], 4, str(path)))
        ])
        assert cache.get_metadata(stat.st_dev, stat.st_ino, stat.st_mtime) == (
            ["Person/Ada"], 4, str(path))
    finally:
        cache.lmdb_close()


@pytest.mark.parametrize(
    ("extension", "legacy_usable"),
    [(".jpg", True), (".png", False), (".webp", False), (".nrw", False)])
def test_legacy_orientation_sensitive_thumbnails_are_regenerated(
        qapp, tmp_path, monkeypatch, extension, legacy_usable):
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    path = tmp_path / f"image{extension}"
    path.touch()
    stat = path.stat()
    inode = struct.pack("Q", stat.st_ino)
    image = QImage(16, 16, QImage.Format_RGB32)
    image.fill(Qt.red)
    cache = imagescanner.ThumbnailCache()
    try:
        path_bytes = str(path).encode()
        payload = (struct.pack("d", stat.st_mtime) + b"PTH\0" +
                   struct.pack("I", len(path_bytes)) + path_bytes +
                   cache._image_to_bytes(image))
        with cache._lmdb_env.begin(write=True) as txn:
            db = cache._get_device_db(stat.st_dev, 128, write=True, txn=txn)
            txn.put(inode, payload, db=db)
        assert bool(cache.get_thumbnail(str(path), 128).image) == legacy_usable

        if not legacy_usable:
            cache._batch_write_to_lmdb([
                (stat.st_dev, inode, image, stat.st_mtime, 128, str(path))])
            assert cache.get_thumbnail(str(path), 128).image
    finally:
        cache.lmdb_close()


def test_invalidation_waits_for_inflight_disk_write(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    path = tmp_path / "image.png"
    image = QImage(16, 16, QImage.Format_RGB32)
    image.fill(Qt.red)
    assert image.save(str(path))
    stat = path.stat()
    other_path = tmp_path / "other.png"
    assert image.save(str(other_path))
    other_stat = other_path.stat()
    cache = imagescanner.ThumbnailCache()
    writing = threading.Event()
    release = threading.Event()
    invalidated = threading.Event()
    original_write = cache._batch_write_to_lmdb

    def delayed_write(batch):
        writing.set()
        if not release.wait(10):
            raise TimeoutError("thumbnail write was not released")
        original_write(batch)

    monkeypatch.setattr(cache, "_batch_write_to_lmdb", delayed_write)
    thread = None
    try:
        cache.set_thumbnail(str(path), image, stat.st_mtime, 128,
                            inode=stat.st_ino, device_id=stat.st_dev)
        assert writing.wait(5)
        cache.set_thumbnail(str(path), image, stat.st_mtime, 256,
                            inode=stat.st_ino, device_id=stat.st_dev)
        cache.set_thumbnail(str(other_path), image, other_stat.st_mtime, 128,
                            inode=other_stat.st_ino, device_id=other_stat.st_dev)

        def invalidate():
            cache.invalidate_path(str(path))
            invalidated.set()

        thread = threading.Thread(target=invalidate)
        thread.start()
        assert not invalidated.wait(0.1)
        release.set()
        thread.join(5)
        assert invalidated.is_set()
        assert not cache.get_thumbnail(str(path), 128).image
        assert not cache._check_disk_cache(
            str(path), [128, 256], stat.st_mtime, stat.st_dev,
            struct.pack("Q", stat.st_ino)).image
        cache.lmdb_close()
        cache.lmdb_open()
        assert not cache.get_thumbnail(str(path), 256).image
        assert cache._check_disk_cache(
            str(other_path), [128], other_stat.st_mtime,
            other_stat.st_dev, struct.pack("Q", other_stat.st_ino)).image
    finally:
        release.set()
        if thread:
            thread.join(10)
        cache.lmdb_close()


@pytest.mark.parametrize(
    ("force_refresh", "expected_generations"), [(False, 0), (True, 1)])
def test_thumbnail_generator_tracks_cache_hits_and_regeneration(
        qapp, tmp_path, monkeypatch, force_refresh, expected_generations):
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    path = tmp_path / "image.png"
    image = QImage(16, 16, QImage.Format_RGB32)
    image.fill(Qt.red)
    assert image.save(str(path))
    stat = path.stat()
    cache = imagescanner.ThumbnailCache()
    pool = imagescanner.ThreadPoolManager()
    generated = Mock(return_value=image)
    monkeypatch.setattr(imagescanner, "generate_thumbnail", generated)
    generator = None
    try:
        cache.set_thumbnail(str(path), image, stat.st_mtime, 128,
                            inode=stat.st_ino, device_id=stat.st_dev)
        generator = imagescanner.ThumbnailGenerator(
            cache, [str(path)], 128, pool,
            force_thumbnail_refresh=force_refresh)
        generator.start()
        deadline = time.monotonic() + 10
        while generator.isRunning() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert not generator.isRunning()
        assert generated.call_count == expected_generations
        assert generator.generated_count == expected_generations
    finally:
        if generator and generator.isRunning():
            generator.stop()
        cache.lmdb_close()


def test_context_regeneration_replaces_cached_tiers_and_updates_view(
        qapp, tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    path = str(images / "image.png")
    image = QImage(16, 16, QImage.Format_RGB32)
    image.fill(Qt.green)
    assert image.save(path)
    old_image = QImage(16, 16, QImage.Format_RGB32)
    old_image.fill(Qt.red)

    monkeypatch.setattr(app, "CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setattr(app, "HISTORY_PATH", str(tmp_path / "history"))
    monkeypatch.setattr(app, "BOOKMARKS_PATH", str(tmp_path / "bookmarks"))
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(filesystemwatcher, "HAVE_WATCHDOG", False)
    monkeypatch.setattr(metadatamanager, "set_app_modified_callback", lambda _: None)
    monkeypatch.setattr(app.MainWindow, "save_config", lambda self: None)
    cache = imagescanner.ThumbnailCache()
    pool = imagescanner.ThreadPoolManager()
    window = None
    try:
        window = app.MainWindow(cache, [str(images)], pool, None)
        deadline = time.monotonic() + 10
        while (window._is_loading or window.thumbnail_generator is None or
               window.thumbnail_generator.isRunning()) and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        qapp.processEvents()
        assert not window._is_loading
        assert not window.thumbnail_generator.isRunning()

        stat = os.stat(path)
        for size in (128, 256, 512):
            assert cache.set_thumbnail(path, old_image, stat.st_mtime, size,
                                       inode=stat.st_ino, device_id=stat.st_dev)
        cache.mark_broken(path, window._current_thumb_tier, stat.st_mtime,
                          stat.st_ino, stat.st_dev, "old error")
        window.found_items_data[0] = (path, old_image, *window.found_items_data[0][2:])
        item = window.thumbnail_model.itemFromIndex(
            app.QModelIndex(window._path_to_model_index[path]))
        item.setData(old_image, IMAGE_DATA_ROLE)
        window.regenerate_thumbnail(path)
        deadline = time.monotonic() + 10
        while window.thumbnail_generator.isRunning() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        qapp.processEvents()
        assert not window.thumbnail_generator.isRunning()
        assert window.thumbnail_generator.generated_count == 1
        assert window.status_lbl.text() == UITexts.HIGH_RES_GENERATED
        assert item.data(IMAGE_DATA_ROLE) is None
        assert window.found_items_data[0][1] is None
        result = cache.get_thumbnail(path, window._current_thumb_tier)
        assert result.image.pixelColor(0, 0) == image.pixelColor(0, 0)
        assert cache.get_broken_info(path, window._current_thumb_tier,
                                     stat.st_mtime, stat.st_ino, stat.st_dev) is None

        window.status_lbl.setText("unchanged")
        window._start_thumbnail_generator([path], window._current_thumb_tier)
        deadline = time.monotonic() + 10
        while window.thumbnail_generator.isRunning() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        qapp.processEvents()
        assert not window.thumbnail_generator.isRunning()
        assert window.status_lbl.text() == "unchanged"

        cache.lmdb_close()
        cache.lmdb_open()
        result = cache._check_disk_cache(
            path, [window._current_thumb_tier], stat.st_mtime, stat.st_dev,
            struct.pack("Q", stat.st_ino))
        assert result.image.pixelColor(0, 0) == image.pixelColor(0, 0)
        for size in (128, 256, 512):
            if size != window._current_thumb_tier:
                assert not cache._check_disk_cache(
                    path, [size], stat.st_mtime, stat.st_dev,
                    struct.pack("Q", stat.st_ino)).image
    finally:
        if window is not None:
            window.perform_shutdown()
            window.deleteLater()
        else:
            cache.lmdb_close()
        qapp.processEvents()


def test_stale_scanner_results_do_not_start_old_generation(qapp, tmp_path, monkeypatch):
    class Scanner(QObject):
        images_found = Signal(list)
        directories_found = Signal(str, list)
        progress_percent = Signal(int)
        progress_msg = Signal(str)
        more_files_available = Signal(int, int)
        finished_scan = Signal(int)

        def __init__(self, *_args, **_kwargs):
            super().__init__()

        def set_auto_load(self, _enabled):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def isRunning(self):
            return False

    monkeypatch.setattr(app, "CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setattr(app, "HISTORY_PATH", str(tmp_path / "history"))
    monkeypatch.setattr(app, "BOOKMARKS_PATH", str(tmp_path / "bookmarks"))
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(filesystemwatcher, "HAVE_WATCHDOG", False)
    monkeypatch.setattr(metadatamanager, "set_app_modified_callback", lambda _: None)
    monkeypatch.setattr(app.MainWindow, "save_config", lambda self: None)
    monkeypatch.setattr(app, "ImageScanner", Scanner)
    cache = imagescanner.ThumbnailCache()
    pool = imagescanner.ThreadPoolManager()
    window = app.MainWindow(cache, [], pool, None)
    try:
        window.start_scan([str(tmp_path)])
        old_scanner = window.scanner
        window.start_scan([str(tmp_path)])

        old_scanner.images_found.emit([
            (str(tmp_path / "old.png"), None, 1, [], 0, 1, 1)])
        old_scanner.finished_scan.emit(1)

        assert not window.found_items_data
        assert window._is_loading
        assert window.thumbnail_generator is None
    finally:
        window.perform_shutdown()
        window.deleteLater()
        qapp.processEvents()


def test_thousand_placeholders_are_added_before_generation(qapp, tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    for index in range(1000):
        (images / f"{index:04}.png").touch()

    monkeypatch.setattr(app, "CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setattr(app, "HISTORY_PATH", str(tmp_path / "history"))
    monkeypatch.setattr(app, "BOOKMARKS_PATH", str(tmp_path / "bookmarks"))
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(filesystemwatcher, "HAVE_WATCHDOG", False)
    monkeypatch.setattr(metadatamanager, "set_app_modified_callback", lambda _: None)
    monkeypatch.setattr(app.MainWindow, "save_config", lambda self: None)
    monkeypatch.setitem(APP_CONFIG, "generation_threads", 4)
    monkeypatch.setitem(APP_CONFIG, "scan_batch_size", 64)

    generation_started = threading.Event()
    release_generation = threading.Event()

    def run_worker(worker):
        try:
            if worker.target_sizes == []:
                stat = os.stat(worker.path)
                worker.result = (worker.path, None, stat.st_mtime, [], 0,
                                 stat.st_ino, stat.st_dev)
            else:
                generation_started.set()
                release_generation.wait(10)
        finally:
            if worker.emitter:
                worker.emitter.emit_progress()
            if worker.semaphore:
                worker.semaphore.release()

    monkeypatch.setattr(imagescanner.ScannerWorker, "run", run_worker)
    cache = imagescanner.ThumbnailCache()
    pool = imagescanner.ThreadPoolManager()
    window = None
    try:
        window = app.MainWindow(cache, [str(images)], pool, None)
        deadline = time.monotonic() + 15
        while not generation_started.is_set() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert generation_started.is_set(), (
            f"discovered {len(window.scanner.all_files)}, "
            f"loaded {len(window.found_items_data)}, "
            f"model rows {window.proxy_model.rowCount()}")
        assert len(window.found_items_data) == 1000
        assert sum(
            window.proxy_model.index(row, 0).data(ITEM_TYPE_ROLE) == "thumbnail"
            for row in range(window.proxy_model.rowCount())
        ) == 1000
    finally:
        release_generation.set()
        if window is not None:
            window.perform_shutdown()
            window.deleteLater()
        else:
            cache.lmdb_close()
        qapp.processEvents()


def test_scan_populates_all_placeholders_before_prioritized_generation(
        qapp, tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()
    image = QImage(16, 16, QImage.Format_RGB32)
    image.fill(Qt.red)
    for index in reversed(range(40)):
        assert image.save(str(images / f"{index:03}.png"))

    monkeypatch.setattr(app, "CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setattr(app, "HISTORY_PATH", str(tmp_path / "history"))
    monkeypatch.setattr(app, "BOOKMARKS_PATH", str(tmp_path / "bookmarks"))
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(filesystemwatcher, "HAVE_WATCHDOG", False)
    monkeypatch.setattr(metadatamanager, "set_app_modified_callback", lambda _: None)
    monkeypatch.setattr(app.MainWindow, "save_config", lambda self: None)
    monkeypatch.setitem(APP_CONFIG, "scan_full_on_start", False)
    monkeypatch.setitem(APP_CONFIG, "scan_batch_size", 16)
    monkeypatch.setitem(APP_CONFIG, "generation_threads", 1)

    first_started = threading.Event()
    release_first = threading.Event()
    calls = []

    def generate(path, size, fd=None):
        calls.append(path)
        if len(calls) == 1:
            first_started.set()
            if not release_first.wait(10):
                raise TimeoutError("thumbnail test did not release first worker")
        return image.copy()

    monkeypatch.setattr(imagescanner, "generate_thumbnail", generate)
    cache = imagescanner.ThumbnailCache()
    pool = imagescanner.ThreadPoolManager()
    window = None
    try:
        window = app.MainWindow(cache, [str(images)], pool, None)
        deadline = time.monotonic() + 10
        while not first_started.is_set() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert first_started.is_set()
        assert not window._is_loading
        assert len(window.found_items_data) == 40
        assert sum(
            window.proxy_model.index(row, 0).data(ITEM_TYPE_ROLE) == "thumbnail"
            for row in range(window.proxy_model.rowCount())
        ) == 40
        assert calls[0] in window._viewport_thumbnail_paths()

        window.thumbnail_view.scrollToBottom()
        QTest.qWait(100)
        visible = window._viewport_thumbnail_paths()
        assert visible
        assert str(images / "039.png") in visible
        assert calls[0] not in visible
        window._prioritize_visible_thumbnails()
        release_first.set()

        deadline = time.monotonic() + 30
        while window.thumbnail_generator.isRunning() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert not window.thumbnail_generator.isRunning(), (
            f"generated {len(calls)} thumbnails; pool active "
            f"{pool.get_pool().activeThreadCount()}")
        assert calls[1] in visible
        assert len(calls) == len(set(calls)) == 40
    finally:
        release_first.set()
        if window is not None:
            window.perform_shutdown()
            window.deleteLater()
        else:
            cache.lmdb_close()
        qapp.processEvents()


@pytest.mark.parametrize("scan_max_level", [0, 2])
@pytest.mark.parametrize("filmstrip_state", ["visible", "during_generation", "after_generation"])
@pytest.mark.parametrize("filmstrip_position", ["bottom", "left"])
def test_direct_viewer_filmstrip_loads_and_prioritizes_visible_thumbnails(
        qapp, tmp_path, monkeypatch, scan_max_level, filmstrip_state,
        filmstrip_position):
    images = tmp_path / "images"
    images.mkdir()
    image = QImage(16, 16, QImage.Format_RGB32)
    image.fill(Qt.red)
    paths = [str(images / f"{index:03}.png") for index in range(40)]
    for path in paths:
        assert image.save(path)

    monkeypatch.setattr(app, "CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setattr(app, "HISTORY_PATH", str(tmp_path / "history"))
    monkeypatch.setattr(app, "BOOKMARKS_PATH", str(tmp_path / "bookmarks"))
    monkeypatch.setattr(imagescanner, "APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(imagescanner, "CACHE_PATH", str(tmp_path / "cache"))
    monkeypatch.setattr(filesystemwatcher, "HAVE_WATCHDOG", False)
    monkeypatch.setattr(metadatamanager, "set_app_modified_callback", lambda _: None)
    monkeypatch.setattr(app.MainWindow, "save_config", lambda self: None)
    monkeypatch.setattr(app.ImageViewer, "inhibit_screensaver", lambda self: None)
    monkeypatch.setattr(app.ImageViewer, "uninhibit_screensaver", lambda self: None)
    monkeypatch.setitem(APP_CONFIG, "scan_max_level", scan_max_level)
    monkeypatch.setitem(APP_CONFIG, "generation_threads", 1)
    (tmp_path / "config").write_text(
        json.dumps({"show_filmstrip": filmstrip_state == "visible",
                    "filmstrip_position": filmstrip_position}))

    first_started = threading.Event()
    release_first = threading.Event()
    calls = []
    generate_thumbnail = imagescanner.generate_thumbnail

    def generate(path, size, fd=None):
        calls.append(path)
        if len(calls) == 1:
            first_started.set()
            if not release_first.wait(10):
                raise TimeoutError("filmstrip test did not release first worker")
        return generate_thumbnail(path, size, fd=fd)

    monkeypatch.setattr(imagescanner, "generate_thumbnail", generate)
    cache = imagescanner.ThumbnailCache()
    pool = imagescanner.ThreadPoolManager()
    window = None
    try:
        cached_path = paths[10]
        stat = os.stat(cached_path)
        cache._batch_write_to_lmdb([
            (stat.st_dev, struct.pack("Q", stat.st_ino), image,
             stat.st_mtime, 128, cached_path)])
        window = app.MainWindow(cache, [paths[0]], pool, None)
        deadline = time.monotonic() + 10
        while not first_started.is_set() and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert first_started.is_set()
        viewer = window.active_viewer
        assert not window.isVisible()
        if filmstrip_state != "visible":
            assert viewer.filmstrip.count() == 0
            if filmstrip_state == "after_generation":
                release_first.set()
                deadline = time.monotonic() + 10
                while window.thumbnail_generator.isRunning() and time.monotonic() < deadline:
                    qapp.processEvents()
                    time.sleep(0.005)
                assert not window.thumbnail_generator.isRunning()
            viewer.toggle_filmstrip()
        assert viewer.filmstrip.count() == len(paths)
        assert [viewer.filmstrip.item(i).data(Qt.UserRole)
                for i in range(len(paths))] == paths

        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert viewer.filmstrip.item(10).data(Qt.UserRole + 1)
        viewer.filmstrip.scrollToItem(viewer.filmstrip.item(len(paths) - 1))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
            if viewer.filmstrip.visualItemRect(viewer.filmstrip.item(39)).intersects(
                    viewer.filmstrip.viewport().rect()):
                break
        visible = [
            paths[i] for i in range(len(paths))
            if viewer.filmstrip.visualItemRect(viewer.filmstrip.item(i)).intersects(
                viewer.filmstrip.viewport().rect())]
        assert paths[-1] in visible
        deadline = time.monotonic() + 0.1
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        release_first.set()

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            qapp.processEvents()
            if (not window.thumbnail_generator.isRunning()
                    and all(viewer.filmstrip.item(i).data(Qt.UserRole + 1)
                            for i in range(len(paths)))):
                break
            time.sleep(0.005)
        if filmstrip_state != "after_generation":
            assert calls[1] in visible
        assert set(calls) == set(paths) - {cached_path}
        assert all(viewer.filmstrip.item(i).data(Qt.UserRole + 1)
                   for i in range(len(paths)))
        assert all(
            viewer.filmstrip.item(i).icon().pixmap(16, 16).toImage()
            .pixelColor(8, 8) == Qt.red for i in range(len(paths)))

        first_item = viewer.filmstrip.item(0)
        first_item.setData(Qt.UserRole + 1, False)
        viewer._on_filmstrip_thumb_loaded(0, paths[1], image)
        assert not first_item.data(Qt.UserRole + 1)
        viewer.refresh_after_delete(paths[1:], 0)
        assert [viewer.filmstrip.item(i).data(Qt.UserRole)
                for i in range(len(paths) - 1)] == paths[1:]
    finally:
        release_first.set()
        if window is not None:
            window.perform_shutdown()
            window.deleteLater()
        else:
            cache.lmdb_close()
        qapp.processEvents()
