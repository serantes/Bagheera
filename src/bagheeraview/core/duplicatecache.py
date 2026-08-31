"""
Duplicate Cache and Detection Module for Bagheera.

This module provides the core logic for detecting duplicate images using
perceptual hashing (dHash) and managing a persistent cache of these hashes
and their relationships using LMDB.

Classes:
    DuplicateCache: Manages the LMDB database for hashes and exceptions.
    DuplicateDetector: Background thread that performs the duplicate analysis.
"""
import os
import logging
import struct
import time as time_module
import collections
import shutil
import lmdb
from pathlib import Path
import PIL.Image

from PySide6.QtCore import (
    QObject, QThread, Signal, QMutex, QSemaphore, QReadWriteLock,
    QMutexLocker, QReadLocker, QWriteLocker, QRunnable
)

import imagehash  # For perceptual hashing

from .constants import (
    DUPLICATE_CACHE_PATH, DUPLICATE_HASH_DB_NAME,
    DUPLICATE_EXCEPTIONS_DB_NAME, DUPLICATE_PENDING_DB_NAME,
    DUPLICATE_BKTREE_DB_NAME, DUPLICATE_HASH_TO_FILES_DB_NAME,
    MAX_DHASH_DISTANCE, UITexts
)

logger = logging.getLogger(__name__)

# Result structure for duplicate detection
DuplicateResult = collections.namedtuple(
    'DuplicateResult',
    ['path1', 'path2', 'hash_value', 'is_exception', 'similarity', 'timestamp'])


class HashWorker(QRunnable):
    """Worker to calculate image hash in a thread pool."""
    def __init__(self, path, detector, result_dict, mutex, semaphore):
        super().__init__()
        self.path = path
        self.detector = detector
        self.result_dict = result_dict
        self.mutex = mutex
        self.semaphore = semaphore

    def run(self):
        if self.detector._is_running:
            try:
                # imagehash requires a PIL/Pillow image object.
                with PIL.Image.open(self.path) as pil_img:
                    # Using dHash from imagehash library as default
                    h = str(imagehash.dhash(pil_img))
                    with QMutexLocker(self.mutex):
                        self.result_dict[self.path] = h
            except Exception as e:
                logger.warning(f"HashWorker failed for {self.path}: {e}")
        self.semaphore.release()


class DuplicateCache(QObject):
    """
    Manages a persistent LMDB cache for perceptual hashes and duplicate relationships.
    Uses (device_id, inode) as primary keys for robustness against file renames/moves.
    """  # noqa: E501

    def __init__(self):
        super().__init__()
        self._lmdb_env = None
        self._hash_db = None
        self._exceptions_db = None
        self._pending_db = None
        self._bktree_db = None
        self._hash_to_files_db = None
        self._db_lock = QMutex()  # Protects LMDB transactions
        # In-memory cache for hashes: (dev, inode) -> (hash_value, mtime, path)
        self._hash_cache = {}
        self._hash_cache_lock = QReadWriteLock()

        self.lmdb_open()

    def lmdb_open(self):
        cache_dir = Path(DUPLICATE_CACHE_PATH)
        cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._lmdb_env = lmdb.open(
                DUPLICATE_CACHE_PATH,
                map_size=10 * 1024 * 1024 * 1024,  # 10GB default
                # Hashes, exceptions, pending, bktree, hash_to_files
                max_dbs=5,
                readonly=False,
                create=True
            )
            self._hash_db = self._lmdb_env.open_db(DUPLICATE_HASH_DB_NAME)
            self._exceptions_db = self._lmdb_env.open_db(DUPLICATE_EXCEPTIONS_DB_NAME)
            self._pending_db = self._lmdb_env.open_db(DUPLICATE_PENDING_DB_NAME)
            self._bktree_db = self._lmdb_env.open_db(DUPLICATE_BKTREE_DB_NAME)
            self._hash_to_files_db = self._lmdb_env.open_db(
                DUPLICATE_HASH_TO_FILES_DB_NAME,
                dupsort=True)
            logger.info(f"Duplicate LMDB cache opened: {DUPLICATE_CACHE_PATH}")
        except Exception as e:
            logger.error(f"Failed to open duplicate LMDB cache: {e}")
            self._lmdb_env = None

    def lmdb_close(self):
        if self._lmdb_env:
            self._lmdb_env.close()
            self._lmdb_env = None
            self._hash_db = None
            self._exceptions_db = None
            self._pending_db = None
            self._bktree_db = None
            self._hash_to_files_db = None

    def get_hash_stats(self):
        """Returns (count, size_bytes) for the hash database."""
        count = 0
        if not self._lmdb_env:
            return 0, 0

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                count = txn.stat(db=self._hash_db)['entries']

        size = 0
        disk_path = os.path.join(DUPLICATE_CACHE_PATH, "data.mdb")
        if os.path.exists(disk_path):
            size = os.path.getsize(disk_path)

        return count, size

    def clear_hashes(self):
        """Clears all hashes from the database by recreating the environment."""
        with QWriteLocker(self._hash_cache_lock):
            self._hash_cache.clear()

        self.lmdb_close()
        try:
            if os.path.exists(DUPLICATE_CACHE_PATH):
                shutil.rmtree(DUPLICATE_CACHE_PATH)
            self.lmdb_open()
            logger.info("Duplicate hash cache cleared.")
        except Exception as e:
            logger.error(f"Error clearing duplicate LMDB: {e}")

    def clear_exceptions(self):
        """Clears all entries from the exceptions database."""
        if not self._lmdb_env or self._exceptions_db is None:
            return False
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                # Clear the DB but keep the handle valid
                txn.drop(self._exceptions_db, delete=False)
        logger.info("Duplicate exceptions database cleared.")
        return True

    def clear_pending(self):
        """Clears all entries from the pending duplicates search database."""
        if not self._lmdb_env or self._pending_db is None:
            return False
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                # Clear the DB but keep the handle valid
                txn.drop(self._pending_db, delete=False)
        logger.info("Duplicate pending search cache cleared.")
        return True

    def set_pending_scan_metadata(self, threshold):
        """Stores scan completion metadata for pending duplicates database."""
        if not self._lmdb_env or self._pending_db is None:
            return False
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                txn.put(b"__scan_completed_threshold__", str(threshold).encode('utf-8'), db=self._pending_db)
        logger.info(f"Duplicate scan metadata saved for threshold {threshold}.")
        return True

    def is_pending_scan_completed(self, threshold):
        """Checks if a pending scan was previously completed for the given threshold."""
        if not self._lmdb_env or self._pending_db is None:
            return False
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                val = txn.get(b"__scan_completed_threshold__", db=self._pending_db)
                if val is not None:
                    try:
                        saved_thresh = int(val.decode('utf-8'))
                        return saved_thresh == int(threshold)
                    except Exception:
                        return False
        return False

    def __del__(self):
        self.lmdb_close()

    @staticmethod
    def _get_inode_info(path):
        try:
            if not path:
                return 0, None
            stat_info = os.stat(path)
            return stat_info.st_dev, struct.pack('Q', stat_info.st_ino)
        except OSError:
            return 0, None

    @staticmethod
    def _hash_str_to_bytes(hash_str):
        return struct.pack('>Q', int(hash_str, 16))

    @staticmethod
    def _hamming_distance(h1_bytes, h2_bytes):
        return bin(struct.unpack('>Q', h1_bytes)[0] ^
                   struct.unpack('>Q', h2_bytes)[0]).count('1')

    def _get_lmdb_key(self, dev_id, inode_key_bytes):
        return f"{dev_id}-{inode_key_bytes.hex()}".encode('utf-8')

    def get_hash_and_path(self, dev_id, inode_key_bytes):
        """Retrieves hash, mtime and path for a given (dev_id, inode_key_bytes)."""
        # Check in-memory cache first
        with QReadLocker(self._hash_cache_lock):
            cached_data = self._hash_cache.get((dev_id, inode_key_bytes))
            if cached_data:
                return cached_data  # (hash_value, mtime, path)

        # Check LMDB
        if not self._lmdb_env:
            return None, 0, None

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                lmdb_key = self._get_lmdb_key(dev_id, inode_key_bytes)
                value_bytes = txn.get(lmdb_key, db=self._hash_db)
                if value_bytes:
                    # Handle format "hash_value_str|mtime|path_str" or old "hash|path"
                    parts = value_bytes.decode('utf-8').split('|', 2)
                    if len(parts) == 3:
                        hash_str = parts[0]
                        mtime_str = parts[1]
                        path_str = os.path.abspath(os.path.normpath(parts[2]))
                        mtime = float(mtime_str)
                    elif len(parts) == 2:
                        hash_str = parts[0]
                        path_str = os.path.abspath(os.path.normpath(parts[1]))
                        mtime = 0.0  # Force re-hash
                    else:
                        return None, 0, None

                    with QWriteLocker(self._hash_cache_lock):
                        self._hash_cache[(dev_id, inode_key_bytes)] = (
                            hash_str, mtime, path_str)
                    return hash_str, mtime, path_str
        return None, 0, None

    def get_hash_info_for_path(self, path, current_mtime, dev_id=None,
                               inode_key_bytes=None):
        if dev_id is None or inode_key_bytes is None:
            dev_id, inode_key_bytes = self._get_inode_info(path)
        if not inode_key_bytes:
            return None, 0, None
        hash_value, cached_mtime, cached_path = self.get_hash_and_path(
            dev_id,
            inode_key_bytes)
        # Return hash only if mtime matches (with small float tolerance)
        if hash_value and abs(cached_mtime - current_mtime) < 0.001:
            return hash_value, cached_mtime, cached_path
        return None, 0, None

    def add_hash_for_path(self,
                          path, hash_value, mtime, dev_id=None, inode_key_bytes=None):
        if dev_id is None or inode_key_bytes is None:  # noqa: E501

            dev_id, inode_key_bytes = self._get_inode_info(path)
        if not inode_key_bytes or not self._lmdb_env:
            return False

        hash_bytes = self._hash_str_to_bytes(hash_value)
        file_id_bytes = f"{dev_id}-{inode_key_bytes.hex()}".encode('utf-8')

        path = os.path.abspath(os.path.normpath(path))
        value_str = f"{hash_value}|{mtime}|{path}"
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                lmdb_key = self._get_lmdb_key(dev_id, inode_key_bytes)

                # Check if the file already had a different hash (update)
                old_val = txn.get(lmdb_key, db=self._hash_db)
                if old_val:
                    old_parts = old_val.decode('utf-8').split('|')
                    if old_parts[0] != hash_value:  # noqa: E501
                        old_h_bytes = self._hash_str_to_bytes(old_parts[0])
                        txn.delete(old_h_bytes,
                                   file_id_bytes, db=self._hash_to_files_db)

                txn.put(lmdb_key, value_str.encode('utf-8'), db=self._hash_db)
                txn.put(hash_bytes, file_id_bytes, db=self._hash_to_files_db)

                # Incremental update of the persistent BK-Tree
                self._persistent_bktree_add(txn, hash_bytes)  # noqa: E501

        with QWriteLocker(self._hash_cache_lock):
            self._hash_cache[(dev_id, inode_key_bytes)] = (hash_value, mtime, path)
        return True

    def add_hashes_batch(self, items, progress_callback=None):
        """
        Batches multiple hash additions into a single LMDB transaction.
        items is a list of tuples: (path, hash_value, mtime, dev_id, inode_key_bytes)
        """
        if not items or not self._lmdb_env:
            return

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                for idx, item in enumerate(items):
                    p, hash_value, mtime, dev_id, inode_key_bytes = item
                    if dev_id is None or inode_key_bytes is None:
                        dev_id, inode_key_bytes = self._get_inode_info(p)
                    if not inode_key_bytes:
                        continue

                    hash_bytes = self._hash_str_to_bytes(hash_value)
                    file_id_bytes = f"{dev_id}-{inode_key_bytes.hex()}".encode('utf-8')
                    norm_p = os.path.abspath(os.path.normpath(p))
                    value_str = f"{hash_value}|{mtime}|{norm_p}"

                    lmdb_key = self._get_lmdb_key(dev_id, inode_key_bytes)
                    old_val = txn.get(lmdb_key, db=self._hash_db)
                    if old_val:
                        old_parts = old_val.decode('utf-8').split('|')
                        if old_parts[0] != hash_value:
                            old_h_bytes = self._hash_str_to_bytes(old_parts[0])
                            txn.delete(old_h_bytes, file_id_bytes, db=self._hash_to_files_db)

                    txn.put(lmdb_key, value_str.encode('utf-8'), db=self._hash_db)
                    txn.put(hash_bytes, file_id_bytes, db=self._hash_to_files_db)
                    self._persistent_bktree_add(txn, hash_bytes)

                    if progress_callback:
                        progress_callback(idx + 1, len(items), norm_p)

        with QWriteLocker(self._hash_cache_lock):
            for item in items:
                p, hash_value, mtime, dev_id, inode_key_bytes = item
                if dev_id and inode_key_bytes:
                    norm_p = os.path.abspath(os.path.normpath(p))
                    self._hash_cache[(dev_id, inode_key_bytes)] = (hash_value, mtime, norm_p)

    def _persistent_bktree_add(self, txn, hash_bytes):
        root_hash = txn.get(b'__root__', db=self._bktree_db)
        if root_hash is None:
            txn.put(b'__root__', hash_bytes, db=self._bktree_db)
            return

        curr_hash = root_hash
        while True:
            if curr_hash == hash_bytes:
                return
            dist = self._hamming_distance(hash_bytes, curr_hash)
            children = self._decode_children(txn.get(curr_hash, db=self._bktree_db))

            if dist in children:
                curr_hash = children[dist]
            else:
                children[dist] = hash_bytes
                txn.put(curr_hash, self._encode_children(children), db=self._bktree_db)
                break

    def persistent_bktree_query(self, hash_str, max_dist):
        """Searches the disk tree for similar hashes."""
        hash_bytes = self._hash_str_to_bytes(hash_str)
        results = []
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                root = txn.get(b'__root__', db=self._bktree_db)
                if not root:
                    return []
                candidates = [root]
                while candidates:
                    curr = candidates.pop()
                    dist = self._hamming_distance(hash_bytes, curr)
                    if dist <= max_dist:
                        results.append((curr, dist))
                    children = self._decode_children(txn.get(curr, db=self._bktree_db))
                    for d, child_hash in children.items():
                        if abs(dist - d) <= max_dist:
                            candidates.append(child_hash)
        return results

    def regenerate_bktree(self, progress_callback=None):
        """
        Regenerates the BK-Tree and reverse index from the hashes database.
        Useful if index corruption is suspected.
        """
        if not self._lmdb_env:
            return False

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                # 1. Clear existing indices (keeps handles valid)
                txn.drop(self._bktree_db, delete=False)
                txn.drop(self._hash_to_files_db, delete=False)

                # 2. Iterate hashes and rebuild
                cursor = txn.cursor(db=self._hash_db)
                count = 0
                total = txn.stat(db=self._hash_db)['entries']
                hashes_added_to_tree = set()

                for file_id_bytes, value_bytes in cursor:
                    try:
                        val_str = value_bytes.decode('utf-8')
                        parts = val_str.split('|')
                        if not parts:
                            continue

                        hash_str = parts[0]
                        hash_bytes = self._hash_str_to_bytes(hash_str)

                        if hash_bytes not in hashes_added_to_tree:
                            self._persistent_bktree_add(txn, hash_bytes)
                            hashes_added_to_tree.add(hash_bytes)

                        txn.put(hash_bytes, file_id_bytes, db=self._hash_to_files_db)

                        count += 1
                        if progress_callback and count % 100 == 0:
                            progress_callback(count, total)
                    except Exception as e:
                        logger.error(f"Error re-indexing {file_id_bytes}: {e}")
        return True

    def get_files_for_hash(self, hash_bytes):
        """Returns all files that share a hash using the reverse index.
        """  # noqa: E501
        files = []
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                cursor = txn.cursor(db=self._hash_to_files_db)
                if cursor.set_key(hash_bytes):
                    for file_id_bytes in cursor.iternext_dup():
                        info = txn.get(file_id_bytes, db=self._hash_db)
                        if info:
                            parts = info.decode('utf-8').split('|')
                            if len(parts) >= 3:
                                fid_str = file_id_bytes.decode('utf-8')
                                dev = int(fid_str.split('-')[0])
                                inode = bytes.fromhex(fid_str.split('-')[1])
                                files.append((parts[2], dev, inode))
        return files

    def check_reverse_index_integrity(self):
        """
        Performs a diagnostic of the reverse index.
        Returns a dictionary with the count of total and orphaned entries.
        """
        stats = {'total': 0, 'orphans': 0, 'mismatches': 0}
        if not self._lmdb_env:
            return stats

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                cursor = txn.cursor(db=self._hash_to_files_db)
                for hash_bytes, file_id_bytes in cursor:
                    stats['total'] += 1
                    info = txn.get(file_id_bytes, db=self._hash_db)
                    if not info:
                        stats['orphans'] += 1
                        continue

                    try:
                        stored_hash_str = info.decode('utf-8').split('|')[0]
                        if self._hash_str_to_bytes(stored_hash_str) != hash_bytes:
                            stats['mismatches'] += 1
                    except Exception:
                        stats['orphans'] += 1
        return stats

    def prune_reverse_index_orphans(self):
        """Removes orphaned records from the reverse index surgically
        without rebuilding the entire tree.
        """
        removed = 0
        if not self._lmdb_env:
            return 0

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                cursor = txn.cursor(db=self._hash_to_files_db)
                for hash_bytes, file_id_bytes in cursor:
                    info = txn.get(file_id_bytes, db=self._hash_db)
                    should_delete = False
                    if not info:
                        should_delete = True
                    else:
                        stored_hash_str = info.decode('utf-8').split('|')[0]
                        if self._hash_str_to_bytes(stored_hash_str) != hash_bytes:
                            should_delete = True

                    if should_delete:
                        cursor.delete()
                        removed += 1
        return removed

    @staticmethod
    def _decode_children(data):
        if not data:
            return {}
        res = {}
        for i in range(0, len(data), 9):
            res[data[i]] = data[i+1:i+9]
        return res

    @staticmethod
    def _encode_children(children_dict):
        res = bytearray()
        for d, h in children_dict.items():
            res.append(d)
            res.extend(h)
        return bytes(res)

    def remove_hash_for_path(self, path, clear_relationships=True):
        """
        Removes the hash entry for a path.

        Args:
            path: File path.
            clear_relationships: If True, also wipes all entries in pending and
                               exceptions DBs involving this file.
        """
        dev_id, inode_key_bytes = self._get_inode_info(path)
        if not inode_key_bytes or not self._lmdb_env:
            return False

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                lmdb_key = self._get_lmdb_key(dev_id, inode_key_bytes)

                # Safeguard: Do not proceed if identity information is invalid
                if dev_id == 0 or not inode_key_bytes:
                    return False

                # Clear the reverse index before removing the main entry
                val_bytes = txn.get(lmdb_key, db=self._hash_db)
                if val_bytes:
                    try:
                        parts = val_bytes.decode('utf-8').split('|')
                        h_bytes = self._hash_str_to_bytes(parts[0])
                        txn.delete(h_bytes, lmdb_key, db=self._hash_to_files_db)
                    except Exception:
                        pass

                txn.delete(lmdb_key, db=self._hash_db)

        with QWriteLocker(self._hash_cache_lock):
            self._hash_cache.pop((dev_id, inode_key_bytes), None)

        # Also remove any exceptions involving this path
        if clear_relationships:
            self._remove_pair_entries_for_path(
                dev_id, inode_key_bytes, self._exceptions_db)
            self._remove_pair_entries_for_path(
                dev_id, inode_key_bytes, self._pending_db)
        return True

    def _get_pair_lmdb_key_from_ids(self, dev1, inode1, dev2, inode2):
        # Ensure canonical order for exception keys
        key_parts = sorted([f"{dev1}-{inode1.hex()}", f"{dev2}-{inode2.hex()}"])
        return f"{key_parts[0]}-{key_parts[1]}".encode('utf-8')

    def _get_pair_lmdb_key(self, path1, path2):
        dev1, inode1 = self._get_inode_info(path1)
        dev2, inode2 = self._get_inode_info(path2)
        if not inode1 or not inode2:
            return None
        return self._get_pair_lmdb_key_from_ids(dev1, inode1, dev2, inode2)

    def mark_as_exception(self,
                          path1, path2, is_exception=True, similarity=None,
                          timestamp=None):
        if not self._lmdb_env:
            return False

        dev1, inode1 = self._get_inode_info(path1)
        dev2, inode2 = self._get_inode_info(path2)
        if not inode1 or not inode2:
            return False

        exception_key = self._get_pair_lmdb_key_from_ids(
            dev1, inode1, dev2, inode2)
        if not exception_key:
            return False

        # Store paths in value to make exception recovery independent of hash DB
        ts = timestamp if timestamp is not None else int(time_module.time())
        val_str = f"{path1}|{path2}|{similarity if similarity is not None else ''}|{ts}"
        value = val_str.encode('utf-8')

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                if is_exception:
                    txn.put(exception_key, value, db=self._exceptions_db)
                else:
                    txn.delete(exception_key, db=self._exceptions_db)
        return True

    def is_exception(self, path1, path2):
        if not self._lmdb_env:
            return False

        dev1, inode1 = self._get_inode_info(path1)
        dev2, inode2 = self._get_inode_info(path2)
        if not inode1 or not inode2:
            return False

        exception_key = self._get_pair_lmdb_key_from_ids(
            dev1, inode1, dev2, inode2)
        if not exception_key:
            return False

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                return txn.get(exception_key, db=self._exceptions_db) is not None

    def _remove_pair_entries_for_path(self,
                                      target_dev, target_inode, db_handle, txn=None):
        """Removes all entries involving a specific (dev, inode) pair from a
        pair-based DB."""
        if not self._lmdb_env:
            return

        target_inode_hex = target_inode.hex()

        def do_remove(t):
            cursor = t.cursor(db=db_handle)
            keys_to_delete = []
            for key_bytes, _ in cursor:  # noqa: E501

                key_str = key_bytes.decode('utf-8')
                parts = key_str.split('-')
                if len(parts) < 4:
                    continue
                dev1, inode1_hex, dev2, inode2_hex = int(
                    parts[0]), parts[1], int(parts[2]), parts[3]
                if (dev1 == target_dev and inode1_hex == target_inode_hex) or \
                   (dev2 == target_dev and inode2_hex == target_inode_hex):
                    keys_to_delete.append(key_bytes)
            for key in keys_to_delete:
                t.delete(key, db=db_handle)

        if txn:
            do_remove(txn)
        else:
            with QMutexLocker(self._db_lock):
                with self._lmdb_env.begin(write=True) as t:
                    do_remove(t)

    def mark_as_pending(self,
                        path1, path2, is_pending=True, similarity=None, timestamp=None):
        """Marks a pair as pending review."""
        if not self._lmdb_env or self._pending_db is None:
            return False

        key = self._get_pair_lmdb_key(path1, path2)
        if not key:
            return False

        # Store paths in value to allow reconstruction without scanning
        ts = timestamp if timestamp is not None else int(time_module.time())
        val_str = f"{path1}|{path2}|{similarity if similarity is not None else ''}|{ts}"
        value = val_str.encode('utf-8')

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                if is_pending:
                    txn.put(key, value, db=self._pending_db)
                else:
                    # Check if it exists before deleting to avoid errors
                    if txn.get(key, db=self._pending_db):
                        txn.delete(key, db=self._pending_db)
        return True

    def mark_as_pending_batch(self, pairs_data):
        """
        Marks multiple pairs as pending review in a single transaction.
        pairs_data: list of (path1, path2, similarity, timestamp)
        """
        if not self._lmdb_env or self._pending_db is None or not pairs_data:
            return False

        with QMutexLocker(self._db_lock):  # noqa: E501

            with self._lmdb_env.begin(write=True) as txn:
                for p1, p2, similarity, timestamp in pairs_data:
                    key = self._get_pair_lmdb_key(p1, p2)
                    if not key:
                        continue

                    ts = timestamp if timestamp is not None else int(time_module.time())
                    sim_str = str(similarity) if similarity is not None else ""
                    val_str = f"{p1}|{p2}|{sim_str}|{ts}"
                    value = val_str.encode('utf-8')
                    txn.put(key, value, db=self._pending_db)
        return True

    def get_all_exceptions_set(self):
        """Returns a set of canonical pairs (frozenset of inode-IDs) marked as
        exceptions."""
        exceptions = set()
        if not self._lmdb_env or self._exceptions_db is None:
            return exceptions
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                cursor = txn.cursor(db=self._exceptions_db)
                for key_bytes, _ in cursor:
                    # Format is dev1-ino1-dev2-ino2. Since ino hex is 16 chars,
                    # we parse from parts knowing that IDs always end with hex.
                    parts = key_bytes.decode('utf-8').split('-')
                    # Handle potential negative dev_ids or other hyphenated parts
                    # Each ID is [device_part] + "-" + [16 hex chars inode]
                    if len(parts) >= 4:
                        id2 = f"{parts[-2]}-{parts[-1]}"
                        id1 = "-".join(parts[:-2])
                        exceptions.add(frozenset((id1, id2)))
        return exceptions

    def get_all_pending_duplicates(self):
        """Retrieves all pending duplicate pairs from the database."""
        results = []
        if not self._lmdb_env or self._pending_db is None:
            return results

        keys_to_delete = []  # Keys to delete from pending DB
        # List to mark exceptions outside the read transaction
        links_to_ignore = []  # noqa: E501

        with QMutexLocker(self._db_lock):  # noqa: E501

            with self._lmdb_env.begin(write=False) as txn:  # noqa: E501

                cursor = txn.cursor(db=self._pending_db)
                for key, value_bytes in cursor:
                    if key.startswith(b"__"):
                        continue
                    try:
                        parts = value_bytes.decode('utf-8').split('|')
                        p1 = Path(parts[0]).resolve()
                        p2 = Path(parts[1]).resolve()

                        # Definitive identity test for symlinks/hardlinks
                        try:
                            if p1.samefile(p2):
                                keys_to_delete.append(key)
                                links_to_ignore.append((str(p1), str(p2)))
                                continue
                        except OSError:
                            # If file doesn't exist, remove from pending
                            keys_to_delete.append(key)
                            pass

                        sim = int(parts[2]) if len(parts) > 2 and parts[2] else None
                        ts = int(parts[3]) if len(parts) > 3 else 0  # noqa: E501
                        if os.path.exists(p1) and os.path.exists(p2):
                            # Check if it's already a known exception (by inode)
                            dev1, ino1 = self._get_inode_info(p1)

                            dev2, ino2 = self._get_inode_info(p2)
                            if ino1 and ino2:
                                ex_key = self._get_pair_lmdb_key_from_ids(
                                    dev1, ino1, dev2, ino2)
                                if txn.get(ex_key, db=self._exceptions_db):
                                    keys_to_delete.append(key)
                                    continue

                            results.append(
                                DuplicateResult(p1, p2, None, False, sim, ts))
                        else:
                            keys_to_delete.append(key)
                    except Exception:
                        keys_to_delete.append(key)
                        continue

            if keys_to_delete:
                try:
                    with self._lmdb_env.begin(write=True) as txn:
                        for k in keys_to_delete:
                            if txn.get(k, db=self._pending_db):
                                txn.delete(k, db=self._pending_db)
                    logger.info(f"Cleaned up {len(keys_to_delete)} invalid "
                                "pending duplicates (files deleted externally)")
                except Exception as e:
                    logger.error(
                        f"Error cleaning up pending duplicates from DB: {e}")

        for p1, p2 in links_to_ignore:
            self.mark_as_exception(p1, p2, True, similarity=100)

        return results

    def get_all_exceptions(self):
        """Retrieves all duplicate pairs marked as exceptions from the database."""
        results = []
        if not self._lmdb_env or self._exceptions_db is None:
            return results

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                cursor = txn.cursor(db=self._exceptions_db)
                for key_bytes, value_bytes in cursor:
                    try:
                        p1, p2 = None, None
                        sim = None
                        ts = 0  # noqa: E501

                        val_str = value_bytes.decode('utf-8')

                        if '|' in val_str:
                            # New format: paths are stored in the value
                            parts = val_str.split('|')
                            if len(parts) >= 2:
                                p1, p2 = parts[0], parts[1]
                                if len(parts) > 2 and parts[2]:
                                    sim = int(parts[2])
                                if len(parts) > 3:  # noqa: E501
                                    ts = int(parts[3])
                                else:
                                    ts = int(os.path.getmtime(p1)) \
                                        if os.path.exists(p1) else 0

                        if not p1 or not p2:
                            # Legacy format fallback: lookup paths in hash db
                            key_str = key_bytes.decode('utf-8')  # noqa: E501
                            kp = key_str.split('-')
                            if len(kp) == 4:
                                k1, k2 = f"{kp[0]}-{kp[1]}".encode(),
                                f"{kp[2]}-{kp[3]}".encode()
                                v1, v2 = txn.get(k1, db=self._hash_db), \
                                    txn.get(k2, db=self._hash_db)
                                if v1 and v2:
                                    # Format is hash|mtime|path|dist... path is always
                                    # index 2
                                    p1 = v1.decode('utf-8').split('|')[2]
                                    p2 = v2.decode('utf-8').split('|')[2]

                        if p1 and p2:
                            if os.path.exists(p1) and os.path.exists(p2):
                                results.append(
                                    DuplicateResult(p1, p2, None, True, sim, ts))
                    except Exception:
                        continue
        return results

    def clean_stale_hashes(self):
        """
        Removes hash entries from the database for files that no longer exist on disk.
        """
        if not self._lmdb_env or self._hash_db is None:
            return 0

        keys_to_delete = []
        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                cursor = txn.cursor(db=self._hash_db)
                for key, value_bytes in cursor:
                    try:
                        # value_bytes is "hash|mtime|path|last_dist"
                        parts = value_bytes.decode('utf-8').split('|')
                        if len(parts) >= 3:
                            path = parts[2]
                            if not os.path.exists(path):
                                keys_to_delete.append(key)
                    except Exception:
                        keys_to_delete.append(key)  # Corrupted entry
                        continue

            if keys_to_delete:
                with self._lmdb_env.begin(write=True) as txn:
                    for k in keys_to_delete:
                        txn.delete(k, db=self._hash_db)
                logger.info(f"Cleaned up {len(keys_to_delete)} stale hash "
                            "entries (files deleted externally)")
        return len(keys_to_delete)

    def get_all_hashes_with_paths(self):
        """Retrieves all hashes from the database along with their associated paths and
        inode info."""
        # hash_value -> [(path, dev_id, inode_key_bytes)]
        all_hashes = collections.defaultdict(list)
        if not self._lmdb_env:
            return all_hashes

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=False) as txn:
                cursor = txn.cursor(db=self._hash_db)
                for key_bytes, value_bytes in cursor:
                    # key_bytes is like "dev_id-inode_hex"
                    key_str = key_bytes.decode('utf-8')
                    parts = key_str.split('-')
                    dev_id = int(parts[0])
                    inode_key_bytes = bytes.fromhex(parts[1])

                    # value_bytes is "hash|mtime|path|last_dist"
                    parts_val = value_bytes.decode('utf-8').split('|')
                    if len(parts_val) >= 3:
                        hash_value = parts_val[0]
                        path = parts_val[2]
                    else:
                        continue

                    all_hashes[hash_value].append((path, dev_id, inode_key_bytes))
        return all_hashes

    def rename_entry(self, old_path, new_path):
        """
        Updates the cache entry for a file that has been renamed or moved.
        This involves deleting the old (dev, inode) entry and adding a new one
        with the new (dev, inode) and path, preserving the hash value.
        """
        old_dev, old_inode_key_bytes = self._get_inode_info(old_path)
        new_dev, new_inode_key_bytes = self._get_inode_info(new_path)

        if not old_inode_key_bytes or not new_inode_key_bytes or not self._lmdb_env:
            return False

        # If the (dev, inode) pair is the same, only the path in the value needs
        # updating.
        # This happens if the file is renamed within the same filesystem.
        if (old_dev, old_inode_key_bytes) == (new_dev, new_inode_key_bytes):
            hash_value, mtime, _ = self.get_hash_and_path(old_dev, old_inode_key_bytes)
            if hash_value:  # noqa: E501

                self.add_hash_for_path(new_path, hash_value, mtime)
                self._update_pair_paths(old_path, new_path, self._pending_db)
                self._update_pair_paths(old_path, new_path, self._exceptions_db)
                return True
            return False

        # If (dev, inode) changed (cross-filesystem move), we need to:
        # 1. Get the hash from the old entry.
        # 2. Remove the old entry.
        # 3. Add a new entry with the new (dev, inode) and path, using the old hash.
        hash_value, mtime, _ = self.get_hash_and_path(old_dev, old_inode_key_bytes)
        if hash_value:
            # Avoid deleting relationships when renaming (only update path)
            # Avoid deleting relationships when renaming (only update path)
            self.remove_hash_for_path(old_path, clear_relationships=False)
            # Adds new (dev, inode) entry
            self.add_hash_for_path(new_path, hash_value, mtime)
            self._update_pair_paths(old_path, new_path, self._pending_db)
            self._update_pair_paths(old_path, new_path, self._exceptions_db)
            return True
        return False

    def _update_pair_paths(self, old_path, new_path, db_handle):
        """Updates stored paths in a pair-based DB value when a file is renamed."""
        if not self._lmdb_env or db_handle is None:
            return

        # Optimization: Pre-calculate the inode ID to filter keys during iteration.
        # Scanning only keys is much faster than retrieving associated values from disk.
        # Scanning only keys is much faster than retrieving associated values from disk.
        dev, ino = self._get_inode_info(old_path)
        if not ino:
            return
        file_id_bytes = f"{dev}-{ino.hex()}".encode('utf-8')

        with QMutexLocker(self._db_lock):
            with self._lmdb_env.begin(write=True) as txn:
                cursor = txn.cursor(db=db_handle)
                # iternext(values=False) iterates only the index keys, avoiding
                # unnecessary I/O.
                for key in cursor.iternext(values=False):  # noqa: E501

                    if file_id_bytes in key:
                        value_bytes = txn.get(key, db=db_handle)
                        if not value_bytes:
                            continue

                        val_str = value_bytes.decode('utf-8')
                        parts = val_str.split('|')  # noqa: E501

                        if len(parts) >= 2:
                            p1, p2 = parts[0], parts[1]  # noqa: E501
                            if p1 == old_path or p2 == old_path:
                                # Update only the path that changed
                                parts[0] = new_path if p1 == old_path else p1
                                parts[1] = new_path if p2 == old_path else p2
                                txn.put(key,
                                        "|".join(parts).encode('utf-8'),
                                        db=db_handle)


class DuplicateDetector(QThread):
    """
    Worker thread for detecting duplicate images using perceptual hashing.
    """
    progress_update = Signal(int, int, str)  # current, total, message
    duplicates_found = Signal(list)  # List of DuplicateResult
    detection_finished = Signal()

    def __init__(self,
                 paths_to_scan, duplicate_cache, pool_manager,
                 method="histogram_hashing", threshold=90, force_full=False):
        super().__init__()
        self.paths_to_scan = paths_to_scan
        self.duplicate_cache = duplicate_cache
        self.pool_manager = pool_manager
        self.method = method
        self.threshold = threshold  # Similarity percentage (50-100)
        self.force_full = force_full
        self._is_running = True

    def stop(self):
        self._is_running = False
        self.wait()  # Add this line

    def run(self):
        # Ensure all paths are absolute and normalized at the start
        self.paths_to_scan = [os.path.abspath(os.path.normpath(p))
                              for p in self.paths_to_scan]

        # Pre-load exceptions to avoid UnboundLocalError in Phase 1 and maintain
        # consistency
        exceptions_set = self.duplicate_cache.get_all_exceptions_set()
        scan_paths_set = set(self.paths_to_scan)

        total_files = len(self.paths_to_scan)
        found_duplicates = []
        # To store frozenset((path1, path2)) for uniqueness
        unique_inode_pairs = set()
        last_ui_update_time = 0

        pool = self.pool_manager.get_pool()

        # 0. Deduplicate input paths by physical identity (symlinks to same file)
        # This avoids comparing a file with its symlink or multiple symlinks to
        # the same target.
        unique_paths_to_scan = []
        canonical_paths = {}  # Initialize canonical_paths dictionary

        for p in self.paths_to_scan:
            try:
                # Resolve symlinks to their real physical location
                rp = os.path.realpath(p)
                if rp not in canonical_paths:
                    canonical_paths[rp] = p
                    unique_paths_to_scan.append(p)
                else:  # noqa: E501

                    # It's a symlink or hardlink to something already in the list.
                    # We mark it as an exception (similarity 100) so it doesn't show up.
                    self.duplicate_cache.mark_as_exception(
                        p, canonical_paths[rp], True, similarity=100)
            except OSError:
                unique_paths_to_scan.append(p)

        total_unique = len(unique_paths_to_scan)
        processed_initial = 0

        # Convert similarity threshold (percentage) to Hamming distance
        distance_threshold = int(MAX_DHASH_DISTANCE * (100 - self.threshold) / 100)
        logger.info(
            f"Duplicate detection: Method={self.method}, "
            f"Similarity Threshold={self.threshold}%, Hamming "
            f"Distance Threshold={distance_threshold}")

        # 2. Phase 1: Hash Collection (Parallelized)
        path_to_hash = {}
        dirty_paths = set()
        paths_to_hash_parallel = []

        for i, path in enumerate(unique_paths_to_scan):
            if not self._is_running:
                break

            try:
                stat_info = os.stat(path)
                mtime = stat_info.st_mtime
                dev, inode = stat_info.st_dev, struct.pack('Q', stat_info.st_ino)

                # Update UI during initial cache check (Phase 1 part A)
                processed_initial += 1
                cached_h, _, cached_path = (
                    self.duplicate_cache.get_hash_info_for_path(
                        path, mtime, dev, inode)
                )

                if cached_h:
                    if cached_path == path:
                        path_to_hash[path] = (cached_h, dev, inode)
                    else:
                        # File moved or renamed: update cache and mark as dirty
                        self.duplicate_cache.add_hash_for_path(
                            path, cached_h, mtime, dev, inode)
                        dirty_paths.add(path)
                        path_to_hash[path] = (cached_h, dev, inode)
                else:
                    dirty_paths.add(path)
                    paths_to_hash_parallel.append((path, mtime, dev, inode))

                current_time = time_module.perf_counter()
                if (current_time - last_ui_update_time > 0.03 or
                        i == 0 or i == total_unique - 1):
                    # Scale Part A to initial 0-10% range of the status bar (0 to 0.2 * total_files)
                    progress = int((processed_initial / total_unique) * (0.2 * total_files))
                    fname = os.path.basename(path)
                    self.progress_update.emit(
                        progress, total_files * 2,
                        UITexts.DUPLICATE_MSG_HASHING.format(filename=fname))
                    last_ui_update_time = current_time

            except OSError:
                continue

        if paths_to_hash_parallel and self._is_running:
            batch_size = pool.maxThreadCount() * 2
            results_mutex = QMutex()
            new_hashes = {}
            sem = QSemaphore(0)

            # Phase 1 part B: Parallel hashing for new/changed files (10% to 50% range)
            num_to_hash = len(paths_to_hash_parallel)
            base_progress = int(0.2 * total_files)
            remaining_progress_span = total_files - base_progress
            processed_hashing = 0

            for i in range(0, num_to_hash, batch_size):
                if not self._is_running:
                    break
                current_batch = paths_to_hash_parallel[i: i + batch_size]
                for p_data in current_batch:
                    pool.start(HashWorker(
                        p_data[0], self, new_hashes, results_mutex, sem))

                for j in range(len(current_batch)):
                    while not sem.tryAcquire(1, 100):
                        if not self._is_running:
                            break
                    if not self._is_running:
                        break
                    processed_hashing += 1
                    current_time = time_module.perf_counter()
                    if (current_time - last_ui_update_time > 0.03 or
                            processed_hashing == num_to_hash):
                        progress = base_progress + int(
                            (processed_hashing / num_to_hash) * remaining_progress_span)
                        fname = os.path.basename(current_batch[j][0])
                        self.progress_update.emit(
                            progress, total_files * 2,
                            UITexts.DUPLICATE_MSG_HASHING.format(filename=fname))
                        last_ui_update_time = current_time

            hashes_to_batch = []
            for p, mtime, dev, inode in paths_to_hash_parallel:
                h = new_hashes.get(p)
                if h:
                    path_to_hash[p] = (h, dev, inode)
                    hashes_to_batch.append((p, h, mtime, dev, inode))

            if hashes_to_batch:
                total_batch = len(hashes_to_batch)
                base_batch_progress = int(0.4 * (total_files * 2))
                span_batch_progress = total_files - base_batch_progress

                def batch_progress_cb(current, total, current_path):
                    nonlocal last_ui_update_time
                    current_time = time_module.perf_counter()
                    if (current_time - last_ui_update_time > 0.03 or
                            current == 1 or current == total):
                        prog = base_batch_progress + int((current / total) * span_batch_progress)
                        fname = os.path.basename(current_path)
                        self.progress_update.emit(
                            prog, total_files * 2,
                            UITexts.DUPLICATE_MSG_HASHING.format(filename=fname))
                        last_ui_update_time = current_time

                self.duplicate_cache.add_hashes_batch(hashes_to_batch, progress_callback=batch_progress_cb)
        elif self._is_running:
            # All files were cached in Phase 1 Part A, advance progress to 50%
            fname = os.path.basename(unique_paths_to_scan[-1]) if unique_paths_to_scan else "..."
            self.progress_update.emit(
                total_files, total_files * 2,
                UITexts.DUPLICATE_MSG_HASHING.format(filename=fname))
            last_ui_update_time = time_module.perf_counter()

        # Load existing pending duplicates (unless force_full)
        if not self.force_full:
            pending = self.duplicate_cache.get_all_pending_duplicates()
            total_pending = len(pending)
            for idx, p in enumerate(pending):
                if not self._is_running:
                    break

                # Progress update during pending duplicate loading (50% to 60% range)
                current_time = time_module.perf_counter()
                if (current_time - last_ui_update_time > 0.03 or
                        idx == 0 or idx == total_pending - 1):
                    progress = total_files + int((idx / total_pending) * (0.2 * total_files)) \
                        if total_pending > 0 else total_files
                    fname = os.path.basename(p.path1)
                    self.progress_update.emit(
                        progress, total_files * 2,
                        UITexts.DUPLICATE_MSG_ANALYZING.format(filename=fname))
                    last_ui_update_time = current_time

                # Normalize database paths to ensure match with scan set
                np1, np2 = (os.path.abspath(os.path.normpath(p.path1)),
                            os.path.abspath(os.path.normpath(p.path2)))

                if np1 in scan_paths_set and np2 in scan_paths_set:
                    # If any of the files changed (is in dirty_paths), the pending
                    # result is invalid and must be ignored for recalculation.
                    if np1 in dirty_paths or np2 in dirty_paths:
                        continue

                    # Fast inode lookup from in-memory path_to_hash when possible
                    h1_tuple = path_to_hash.get(np1)
                    dev1, ino1 = (h1_tuple[1], h1_tuple[2]) if h1_tuple else self.duplicate_cache._get_inode_info(np1)
                    h2_tuple = path_to_hash.get(np2)
                    dev2, ino2 = (h2_tuple[1], h2_tuple[2]) if h2_tuple else self.duplicate_cache._get_inode_info(np2)

                    # Skip physical identities (links)
                    if dev1 and dev2 and (dev1, ino1) == (dev2, ino2):
                        self.duplicate_cache.mark_as_exception(
                            np1, np2, True, similarity=100)
                        self.duplicate_cache.mark_as_pending(np1, np2, False)
                        continue

                    # Check if already marked as exception
                    if ino1 and ino2:
                        id1, id2 = f"{dev1}-{ino1.hex()}", f"{dev2}-{ino2.hex()}"
                        if frozenset((id1, id2)) in exceptions_set:
                            # If already an exception, ensure it's not in pending
                            self.duplicate_cache.mark_as_pending(np1, np2, False)
                            continue

                    if p.similarity is None or p.similarity >= self.threshold:
                        # Use normalized paths in the result
                        res = p._replace(path1=np1, path2=np2)
                        found_duplicates.append(res)
                        # Save inodes to avoid recalculating in Phase 2
                        if ino1 and ino2:
                            unique_inode_pairs.add(frozenset((id1, id2)))

        if not self._is_running:
            self.detection_finished.emit()
            return

        # Determine if we can rely on existing pending cache for this threshold
        has_pending_cache = (not self.force_full and self.duplicate_cache.is_pending_scan_completed(self.threshold))

        # --- KEY OPTIMIZATION: EARLY EXIT ---
        # If there are no new or modified files AND we have a valid completed pending scan for this threshold,
        # return results already present in the pending database.
        if not dirty_paths and has_pending_cache:
            self.progress_update.emit(
                total_files * 2, total_files * 2,
                UITexts.DUPLICATE_FINISHED)
            self.duplicates_found.emit(found_duplicates)
            self.detection_finished.emit()
            return

        # 3. Phase 2: Incremental Comparison using Persistent BK-Tree
        paths_to_query = list(dirty_paths) if has_pending_cache \
            else unique_paths_to_scan

        total_queries = len(paths_to_query)
        results_to_save = []
        start_p2_progress = total_files + int(0.2 * total_files)
        span_p2_progress = max(1, (total_files * 2) - start_p2_progress)

        if total_queries > 0 and self._is_running:
            last_ui_update_time = 0  # Force immediate UI update on start of Phase 2
            step_interval = max(1, total_queries // 100)

            for i, p1 in enumerate(paths_to_query):
                if not self._is_running:
                    break

                current_time = time_module.perf_counter()
                if (current_time - last_ui_update_time > 0.03 or
                        i == 0 or
                        i == total_queries - 1 or
                        i % step_interval == 0):
                    progress = start_p2_progress + int(((i + 1) / total_queries) * span_p2_progress)
                    fname = os.path.basename(p1)
                    self.progress_update.emit(
                        progress, total_files * 2,
                        UITexts.DUPLICATE_MSG_ANALYZING.format(filename=fname))
                    last_ui_update_time = current_time

                h1_data = path_to_hash.get(p1)
                if not h1_data:
                    continue
                h1_str, dev1, ino1 = h1_data

                # Query the persistent tree for similar hashes (direct from disk)
                similar_hashes = self.duplicate_cache.persistent_bktree_query(
                    h1_str, distance_threshold)

                for h2_bytes, distance in similar_hashes:
                    # Find all files sharing this similar hash (reverse index)
                    matches = self.duplicate_cache.get_files_for_hash(h2_bytes)

                    for p2, dev2, ino2 in matches:
                        if not self._is_running:
                            break

                        # Keep progress responsive inside inner matching loop as well
                        current_time = time_module.perf_counter()
                        if current_time - last_ui_update_time > 0.03:
                            progress = start_p2_progress + int(((i + 1) / total_queries) * span_p2_progress)
                            fname = os.path.basename(p1)
                            self.progress_update.emit(
                                progress, total_files * 2,
                                UITexts.DUPLICATE_MSG_ANALYZING.format(filename=fname))
                            last_ui_update_time = current_time

                        # Check if p2 is within the current scan scope to avoid
                        # results outside the folders the user is currently browsing.
                        if p2 not in scan_paths_set:
                            continue

                        # 1. Check if it's exactly the same path (already normalized)
                        if p1 == p2:
                            continue

                        # 2. Check memory caches for physical identity (Inodes)
                        id1, id2 = f"{dev1}-{ino1.hex()}", f"{dev2}-{ino2.hex()}"
                        inode_pair = frozenset((id1, id2))

                        if inode_pair in unique_inode_pairs or inode_pair in exceptions_set:
                            continue

                        # 3. Absolute physical identity (pointers to the same object)
                        try:
                            if (dev1, ino1) == (dev2, ino2) or os.path.samefile(p1, p2):
                                # Silent identity (symlinks): mark and skip
                                self.duplicate_cache.mark_as_exception(
                                    p1, p2, True, similarity=100)
                                exceptions_set.add(inode_pair)
                                unique_inode_pairs.add(inode_pair)
                                continue
                        except OSError:
                            pass

                        # 4. Avoid duplicating pairs already processed in this session
                        if inode_pair in unique_inode_pairs:
                            continue

                        # 5. Calculate actual similarity
                        sim = int((1.0 - (distance / MAX_DHASH_DISTANCE)) * 100)
                        if sim < self.threshold:
                            continue

                        ts = int(time_module.time())
                        res = DuplicateResult(p1, p2, h1_str, False, sim, ts)
                        found_duplicates.append(res)
                        unique_inode_pairs.add(inode_pair)
                        results_to_save.append((p1, p2, sim, ts))

                # Periodically flush pending updates to DB
                if len(results_to_save) >= 50:
                    self.duplicate_cache.mark_as_pending_batch(results_to_save)
                    results_to_save = []

        # Final flush of remaining updates
        if results_to_save:
            self.duplicate_cache.mark_as_pending_batch(results_to_save)

        # Emit 100% analyzing status update before finishing
        fname = os.path.basename(paths_to_query[-1]) if paths_to_query else "..."
        self.progress_update.emit(
            total_files * 2, total_files * 2,
            UITexts.DUPLICATE_MSG_ANALYZING.format(filename=fname))

        # Mark scan as completed for this threshold
        self.duplicate_cache.set_pending_scan_metadata(self.threshold)

        self.progress_update.emit(
            total_files * 2, total_files * 2,
            UITexts.DUPLICATE_FINISHED)
        self.duplicates_found.emit(found_duplicates)
        self.detection_finished.emit()


class SimilarSearchWorker(QThread):
    """
    Worker thread to find similar images to a target path.
    Uses BK-Tree query and filters by whitelist/blacklist.
    """
    progress_update = Signal(int, int, str)
    results_found = Signal(list)  # List of (path, similarity)
    finished = Signal()

    def __init__(self, target_path, duplicate_cache, threshold, whitelist_str, blacklist_str):
        super().__init__()
        self.target_path = os.path.abspath(os.path.normpath(target_path))
        self.cache = duplicate_cache
        self.threshold = threshold
        self._is_running = True

        self.whitelist = [os.path.abspath(os.path.expanduser(p.strip()))
                          for p in whitelist_str.split(',') if p.strip()]
        self.blacklist = [os.path.abspath(os.path.expanduser(p.strip()))
                          for p in blacklist_str.split(',') if p.strip()]

    def stop(self):
        self._is_running = False
        self.wait()

    def run(self):
        try:
            st = os.stat(self.target_path)
            h_str, _, _ = self.cache.get_hash_info_for_path(self.target_path, st.st_mtime)

            if not h_str:
                with PIL.Image.open(self.target_path) as img:
                    h_str = str(imagehash.dhash(img))
                    self.cache.add_hash_for_path(self.target_path, h_str, st.st_mtime)

            dist_threshold = int(MAX_DHASH_DISTANCE * (100 - self.threshold) / 100)
            similar_hashes = self.cache.persistent_bktree_query(h_str, dist_threshold)

            results = []
            processed = 0
            total = len(similar_hashes)

            for h_bytes, dist in similar_hashes:
                if not self._is_running:
                    break

                matches = self.cache.get_files_for_hash(h_bytes)
                sim = int((1.0 - (dist / MAX_DHASH_DISTANCE)) * 100)

                for path, dev, inode in matches:
                    if self._is_allowed(path):
                        if os.path.abspath(path) != self.target_path:
                            results.append((path, sim))

                processed += 1
                self.progress_update.emit(processed, total, UITexts.SIMILAR_SEARCH_PROGRESS.format(len(results)))

            results.sort(key=lambda x: x[1], reverse=True)
            self.results_found.emit(results)
        except Exception as e:
            logger.error(f"SimilarSearchWorker error: {e}")
        finally:
            self.finished.emit()

    def _is_allowed(self, path):
        abs_p = os.path.abspath(os.path.normpath(path))
        for b in self.blacklist:
            if abs_p == b or abs_p.startswith(b + os.sep):
                return False
        if not self.whitelist:
            return True
        for w in self.whitelist:
            if abs_p == w or abs_p.startswith(w + os.sep):
                return True
        return False
