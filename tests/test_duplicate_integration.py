import os
from unittest.mock import MagicMock, patch

import pytest
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


def test_detector_ai_phase_merges_pairs(tmp_path):
    """The AI phase upgrades an existing hash pair and adds new AI pairs."""
    file1, file2, file3 = _make_files(tmp_path,
                                      ["f1.png", "f2.png", "f3.png"])
    cache = _make_cache(tmp_path)
    try:
        detector = DuplicateDetector(
            [file1, file2, file3], cache, MagicMock(),
            threshold=90, ai_enabled=True, ai_threshold=90)
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
