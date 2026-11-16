import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from bagheeraview.core.duplicatecache import (
    DuplicateCache, DuplicateDetector, DuplicateResult,
    duplicate_sort_key, merge_duplicate_results,
)
from bagheeraview.core.constants import (
    DUPLICATE_METHOD_HASH, DUPLICATE_METHOD_AI, DUPLICATE_METHOD_BOTH,
)


def get_qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _qapp():
    return get_qapp()


def _make_cache(tmp_path):
    get_qapp()
    db_dir = tmp_path / "test_dup_db"
    os.makedirs(db_dir, exist_ok=True)
    with patch("bagheeraview.core.duplicatecache.DUPLICATE_CACHE_PATH",
               str(db_dir)):
        cache = DuplicateCache()
    return cache


def _make_files(tmp_path, names):
    paths = []
    for name in names:
        p = tmp_path / name
        p.write_bytes(b"dummy")
        paths.append(str(p))
    return paths


def test_merge_duplicate_results_both_methods():
    """A hash record and an AI record for the same pair become 'both'."""
    hash_res = DuplicateResult("/a", "/b", "hash", False, 92, 1,
                               DUPLICATE_METHOD_HASH, None)
    ai_res = DuplicateResult("/a", "/b", None, False, None, 2,
                             DUPLICATE_METHOD_AI, 95)
    merged = merge_duplicate_results(hash_res, ai_res)

    assert merged.method == DUPLICATE_METHOD_BOTH
    assert merged.similarity == 92
    assert merged.ai_similarity == 95


def test_result_sort_key_ordering():
    """Confirmed pairs rank before hash-only and AI-only pairs."""
    both = DuplicateResult("/a", "/b", None, False, 95, 1,
                           DUPLICATE_METHOD_BOTH, 94)
    hash_only = DuplicateResult("/a", "/b", None, False, 95, 1,
                                DUPLICATE_METHOD_HASH, None)
    ai_only = DuplicateResult("/a", "/b", None, False, None, 1,
                              DUPLICATE_METHOD_AI, 93)

    keys = [duplicate_sort_key(both), duplicate_sort_key(hash_only),
            duplicate_sort_key(ai_only)]
    assert keys == sorted(keys, reverse=True)


def test_pending_roundtrip_new_fields(tmp_path):
    """mark_as_pending/get_all_pending_duplicates keep the new metadata."""
    file1, file2 = _make_files(tmp_path, ["f1.png", "f2.png"])
    cache = _make_cache(tmp_path)
    try:
        cache.mark_as_pending(file1, file2, True, similarity=None,
                              method=DUPLICATE_METHOD_AI, ai_similarity=93)
        pending = cache.get_all_pending_duplicates()
        assert len(pending) == 1
        p = pending[0]
        assert p.method == DUPLICATE_METHOD_AI
        assert p.ai_similarity == 93
        assert p.similarity is None
    finally:
        cache.lmdb_close()


def test_pending_merge_same_pair_not_duplicated(tmp_path):
    """The same pair written by both pipelines is stored only once."""
    file1, file2 = _make_files(tmp_path, ["f1.png", "f2.png"])
    cache = _make_cache(tmp_path)
    try:
        cache.mark_as_pending(file1, file2, True, similarity=90)
        cache.mark_as_pending(file1, file2, True, similarity=90,
                              method=DUPLICATE_METHOD_AI, ai_similarity=95)
        pending = cache.get_all_pending_duplicates()
        assert len(pending) == 1
        assert pending[0].method == DUPLICATE_METHOD_BOTH
        assert pending[0].similarity == 90
        assert pending[0].ai_similarity == 95
    finally:
        cache.lmdb_close()


def test_pending_batch_new_fields(tmp_path):
    """mark_as_pending_batch accepts 6-tuples and merges with 4-tuples."""
    file1, file2 = _make_files(tmp_path, ["f1.png", "f2.png"])
    cache = _make_cache(tmp_path)
    try:
        cache.mark_as_pending_batch([(file1, file2, 90, 1234)])
        cache.mark_as_pending_batch(
            [(file1, file2, None, 1235, DUPLICATE_METHOD_AI, 94)])
        pending = cache.get_all_pending_duplicates()
        assert len(pending) == 1
        assert pending[0].method == DUPLICATE_METHOD_BOTH
        assert pending[0].similarity == 90
        assert pending[0].ai_similarity == 94
        assert pending[0].timestamp == 1235
    finally:
        cache.lmdb_close()


def test_pending_legacy_value_parses(tmp_path):
    """Legacy 4-field values are read as hash-only records."""
    file1, file2 = _make_files(tmp_path, ["f1.png", "f2.png"])
    cache = _make_cache(tmp_path)
    try:
        key = cache._get_pair_lmdb_key(file1, file2)
        with cache._lmdb_env.begin(write=True) as txn:
            val = f"{file1}|{file2}|90|1234".encode('utf-8')
            txn.put(key, val, db=cache._pending_db)
        pending = cache.get_all_pending_duplicates()
        assert len(pending) == 1
        assert pending[0].method == DUPLICATE_METHOD_HASH
        assert pending[0].similarity == 90
        assert pending[0].ai_similarity is None
    finally:
        cache.lmdb_close()


def test_legacy_ai_scan_is_rechecked_but_hash_cache_remains_valid(tmp_path):
    cache = _make_cache(tmp_path)
    try:
        with cache._lmdb_env.begin(write=True) as txn:
            txn.put(b"__scan_completed_threshold__", b"90|80",
                    db=cache._pending_db)
        assert cache.is_pending_scan_completed(90)
        assert not cache.is_pending_scan_completed(90, 80)

        cache.set_pending_scan_metadata(90, 80)
        assert cache.is_pending_scan_completed(90, 80)
        assert not cache.is_pending_scan_completed(90, 85)
    finally:
        cache.lmdb_close()


def test_detector_ai_phase_merges_pairs(tmp_path):
    """The AI phase upgrades an existing hash pair and adds new AI pairs."""
    file1, file2, file3 = _make_files(tmp_path,
                                      ["f1.png", "f2.png", "f3.png"])
    cache = _make_cache(tmp_path)
    try:
        detector = DuplicateDetector(
            [file1, file2, file3], cache, MagicMock(),
            threshold=90, ai_enabled=True, ai_threshold=90)
        detector.ai_available = True
        detector.exceptions_set = cache.get_all_exceptions_set()
        detector.scan_paths_set = set(detector.paths_to_scan)
        detector.path_to_hash = {}

        import struct
        st1 = os.stat(file1)
        st2 = os.stat(file2)
        id1 = f"{st1.st_dev}-{struct.pack('Q', st1.st_ino).hex()}"
        id2 = f"{st2.st_dev}-{struct.pack('Q', st2.st_ino).hex()}"
        merged = {
            frozenset((id1, id2)):
                DuplicateResult(file1, file2, "h", False, 92, 1,
                                DUPLICATE_METHOD_HASH, None)
        }
        # The AI phase reports that same pair again plus a new AI-only pair.
        fake_pairs = [(file1, file2, 90), (file2, file3, 93)]
        results_to_save_ai = []

        with patch("bagheeraview.core.faiss_worker.FaissPairSearcher") \
                as MockSearcher:
            mock_searcher = MockSearcher.return_value
            mock_searcher.run.return_value = fake_pairs
            detector._run_ai_phase(merged, results_to_save_ai)

        records = list(merged.values())
        assert len(records) == 2
        methods = sorted(r.method for r in records)
        assert DUPLICATE_METHOD_BOTH in methods
        assert DUPLICATE_METHOD_AI in methods
        assert len(results_to_save_ai) == 2
    finally:
        cache.lmdb_close()


def test_faiss_pair_search_generates_missing_and_stale_vectors(
        tmp_path, monkeypatch):
    from bagheeraview.core import faiss_worker

    paths = [tmp_path / f"{i}.png" for i in range(3)]
    for path in paths:
        Image.new("RGB", (4, 4), "red").save(path)
    monkeypatch.setattr(faiss_worker, "DB_PATH", str(tmp_path / "vectors.db"))
    monkeypatch.setattr(faiss_worker, "_download_model_if_needed", lambda: None)
    vector = np.ones(1024, dtype=np.float32)
    conn = faiss_worker._open_embeddings_db()
    conn.executemany("INSERT INTO embeddings VALUES (?, ?, ?)", [
        (str(paths[0]), paths[0].stat().st_mtime, vector.tobytes()),
        (str(paths[1]), paths[1].stat().st_mtime - 20, vector.tobytes()),
    ])
    conn.commit()
    conn.close()
    embedded = []

    class Embedder:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def embed(self, image):
            embedded.append(image)
            return SimpleNamespace(
                embeddings=[SimpleNamespace(embedding=vector)])

    vision = SimpleNamespace(
        ImageEmbedderOptions=lambda **kwargs: kwargs,
        ImageEmbedder=SimpleNamespace(
            create_from_options=lambda _options: Embedder()))
    python = SimpleNamespace(
        BaseOptions=lambda **kwargs: kwargs, vision=vision)
    mp = SimpleNamespace(
        ImageFormat=SimpleNamespace(SRGB="srgb"),
        Image=lambda **kwargs: kwargs["data"], tasks=SimpleNamespace(python=python))
    monkeypatch.setitem(sys.modules, "mediapipe", mp)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks", mp.tasks)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks.python", python)

    vectors_progress = []
    search_progress = []
    searcher = faiss_worker.FaissPairSearcher(
        [str(p) for p in paths], 90,
        progress_callback=lambda current, total, msg:
            vectors_progress.append((current, total)),
        search_progress_callback=lambda current, total:
            search_progress.append((current, total)))
    assert len(searcher.run()) == 3
    assert len(embedded) == 2
    assert vectors_progress == [(1, 2), (2, 2)]
    assert search_progress == [(0, 3), (3, 3)]

    vectors_progress.clear()
    search_progress.clear()
    assert len(searcher.run()) == 3
    assert len(embedded) == 2
    assert vectors_progress == []
    assert search_progress == [(0, 3), (3, 3)]


def test_faiss_pair_search_reports_multiple_batches(tmp_path, monkeypatch):
    from bagheeraview.core import faiss_worker

    paths = _make_files(tmp_path, [f"{i}.png" for i in range(130)])
    monkeypatch.setattr(faiss_worker, "DB_PATH", str(tmp_path / "vectors.db"))
    conn = faiss_worker._open_embeddings_db()
    vector = np.ones(1024, dtype=np.float32).tobytes()
    conn.executemany("INSERT INTO embeddings VALUES (?, ?, ?)", [
        (path, os.path.getmtime(path), vector) for path in paths])
    conn.commit()
    conn.close()

    class Index:
        def search(self, batch, k):
            return (np.zeros((len(batch), k)), np.full((len(batch), k), -1))

    monkeypatch.setattr(faiss_worker, "_build_faiss_index", lambda _vectors: Index())
    progress = []
    searcher = faiss_worker.FaissPairSearcher(
        paths, 90, search_progress_callback=lambda current, total:
            progress.append((current, total)))

    assert searcher.run() == []
    assert progress == [(0, 130), (128, 130), (130, 130)]


@pytest.mark.parametrize("ai_enabled", [False, True])
@pytest.mark.parametrize("cached_hashes", [False, True])
def test_detector_progress_reserves_ai_phase(
        tmp_path, monkeypatch, ai_enabled, cached_hashes):
    from bagheeraview.core import faiss_worker

    paths = _make_files(tmp_path, [f"{i}.png" for i in range(10)])
    if not cached_hashes:
        for path in paths:
            Image.new("RGB", (4, 4), "red").save(path)
    cache = MagicMock()
    cache.get_all_exceptions_set.return_value = set()
    cache.get_hash_info_for_path.side_effect = (
        lambda path, *_args: ("0" * 16 if cached_hashes else None, None, path))
    cache.get_all_pending_duplicates.return_value = []
    cache.is_pending_scan_completed.return_value = False
    cache.persistent_bktree_query.return_value = []
    cache.add_hashes_batch.side_effect = lambda entries, progress_callback: [
        progress_callback(index, len(entries), entry[0])
        for index, entry in enumerate(entries, 1)]

    class Pool:
        def maxThreadCount(self):
            return 2

        def start(self, worker):
            worker.run()

    class Searcher:
        def __init__(self, *_args, progress_callback,
                     search_progress_callback, **_kwargs):
            self.vectors = progress_callback
            self.search = search_progress_callback

        def run(self):
            self.vectors(1, 2, "ignored")
            self.vectors(2, 2, "ignored")
            self.search(0, 4)
            self.search(2, 4)
            self.search(4, 4)
            return []

    monkeypatch.setattr(faiss_worker, "FaissPairSearcher", Searcher)
    detector = DuplicateDetector(
        paths, cache, SimpleNamespace(get_pool=Pool), ai_enabled=ai_enabled)
    detector.ai_available = True
    updates = []
    detector.progress_update.connect(lambda *args: updates.append(args))
    detector.run()

    values = [current for current, _total, _message in updates]
    assert values == sorted(values)
    assert all(total == len(paths) * (3 if ai_enabled else 2)
               for _current, total, _message in updates)
    if ai_enabled:
        assert [22, 25, 25, 27, 30] == values[-8:-3]
    assert values[-1] == (30 if ai_enabled else 20)


def test_pending_passes_thresholds(tmp_path):
    """AI-only records are rejected when the AI pipeline is disabled."""
    file1, file2 = _make_files(tmp_path, ["f1.png", "f2.png"])
    cache = _make_cache(tmp_path)
    try:
        detector = DuplicateDetector([file1, file2], cache, MagicMock(),
                                     threshold=90, ai_enabled=False)
        ai_res = DuplicateResult(file1, file2, None, False, None, 1,
                                 DUPLICATE_METHOD_AI, 93)
        assert detector._pending_passes_thresholds(ai_res) is False

        detector_ai = DuplicateDetector([file1, file2], cache, MagicMock(),
                                        threshold=90, ai_enabled=True,
                                        ai_threshold=90)
        assert detector_ai._pending_passes_thresholds(ai_res) is True

        hash_res = DuplicateResult(file1, file2, None, False, 91, 1,
                                   DUPLICATE_METHOD_HASH, None)
        assert detector._pending_passes_thresholds(hash_res) is True
    finally:
        cache.lmdb_close()
