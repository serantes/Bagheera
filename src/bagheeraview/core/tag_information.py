"""LMDB storage for tag information and reusable Markdown templates."""

import logging
import os
import uuid

import lmdb

from .constants import TAG_INFO_DB_PATH

logger = logging.getLogger(__name__)

_TEMPLATES_DB = b"templates"
_INFORMATION_DB = b"information"
_TAGS_DB = b"tags"
_MIGRATION_FILE_PREFIX = b"migration:legacy_file:"
_MIGRATION_TEMPLATE_MARKER = b"migration:legacy_template_v1"
_MAP_SIZE = 256 * 1024 * 1024
_STORES = {}


class TagInformationStore:
    """Store tag-to-information associations and templates in named databases."""

    def __init__(self, path=TAG_INFO_DB_PATH):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.env = lmdb.open(
            self.path,
            map_size=_MAP_SIZE,
            max_dbs=3,
            readonly=False,
            create=True,
        )
        self.templates_db = self.env.open_db(_TEMPLATES_DB, create=True)
        self.information_db = self.env.open_db(_INFORMATION_DB, create=True)
        self.tags_db = self.env.open_db(_TAGS_DB, create=True)

    @staticmethod
    def _encode(value):
        return value.encode("utf-8")

    @staticmethod
    def _decode(value):
        return value.decode("utf-8") if value is not None else None

    def get_info_key(self, tag):
        with self.env.begin(db=self.tags_db) as txn:
            return self._decode(txn.get(self._encode(tag)))

    def get_info(self, tag):
        with self.env.begin() as txn:
            info_key = txn.get(self._encode(tag), db=self.tags_db)
            if info_key is None:
                return None
            return self._decode(txn.get(info_key, db=self.information_db))

    def has_info(self, tag):
        return self.get_info_key(tag) is not None

    def save_info(self, tag, markdown):
        tag_key = self._encode(tag)
        with self.env.begin(write=True) as txn:
            info_key = txn.get(tag_key, db=self.tags_db)
            if info_key is None:
                info_key = self._encode(str(uuid.uuid4()))
                txn.put(tag_key, info_key, db=self.tags_db, overwrite=False)
            txn.put(info_key, self._encode(markdown), db=self.information_db)
        return self._decode(info_key)

    def delete_tag(self, tag):
        tag_key = self._encode(tag)
        with self.env.begin(write=True) as txn:
            info_key = txn.get(tag_key, db=self.tags_db)
            if info_key is None:
                return False
            txn.delete(tag_key, db=self.tags_db)
            cursor = txn.cursor(self.tags_db)
            referenced = any(value == info_key for _, value in cursor)
            if not referenced:
                txn.delete(info_key, db=self.information_db)
            return True

    def associate(self, tag, source_tag):
        tag_key = self._encode(tag)
        source_key = self._encode(source_tag)
        with self.env.begin(write=True) as txn:
            new_info_key = txn.get(source_key, db=self.tags_db)
            if new_info_key is None:
                raise KeyError(source_tag)
            old_info_key = txn.get(tag_key, db=self.tags_db)
            if old_info_key == new_info_key:
                return False
            txn.put(tag_key, new_info_key, db=self.tags_db)
            if old_info_key is not None:
                cursor = txn.cursor(self.tags_db)
                if not any(value == old_info_key for _, value in cursor):
                    txn.delete(old_info_key, db=self.information_db)
            return True

    def rename_tag_prefix(self, old_tag, new_tag):
        old_prefix = self._encode(old_tag)
        new_prefix = self._encode(new_tag)
        if (new_prefix == old_prefix
                or new_prefix.startswith(old_prefix + b"/")
                or old_prefix.startswith(new_prefix + b"/")):
            raise ValueError("A tag cannot be renamed into its own path")
        with self.env.begin(write=True) as txn:
            cursor = txn.cursor(self.tags_db)
            entries = [
                (key, value)
                for key, value in cursor
                if key == old_prefix or key.startswith(old_prefix + b"/")
            ]
            if not entries:
                return 0
            moves = [
                (key, new_prefix + key[len(old_prefix):], value)
                for key, value in entries
            ]
            old_keys = {key for key, _, _ in moves}
            for _, destination, _ in moves:
                if destination not in old_keys and txn.get(
                    destination, db=self.tags_db
                ) is not None:
                    raise ValueError(
                        f"Tag information already exists for "
                        f"{self._decode(destination)}"
                    )
            for source, _, _ in moves:
                txn.delete(source, db=self.tags_db)
            for _, destination, value in moves:
                txn.put(destination, value, db=self.tags_db)
            return len(moves)

    def templates(self):
        with self.env.begin(db=self.templates_db) as txn:
            return sorted(
                self._decode(key)
                for key, _ in txn.cursor()
            )

    def get_template(self, name):
        with self.env.begin(db=self.templates_db) as txn:
            return self._decode(txn.get(self._encode(name)))

    def save_template(self, name, markdown):
        if not name.strip():
            raise ValueError("Template name cannot be empty")
        with self.env.begin(write=True, db=self.templates_db) as txn:
            txn.put(self._encode(name.strip()), self._encode(markdown))

    def delete_template(self, name):
        with self.env.begin(write=True, db=self.templates_db) as txn:
            return txn.delete(self._encode(name))

    def tags_with_info(self, filter_text=""):
        needle = filter_text.casefold()
        with self.env.begin() as txn:
            result = []
            cursor = txn.cursor(self.tags_db)
            for tag_key, info_key in cursor:
                if txn.get(info_key, db=self.information_db) is None:
                    continue
                tag = self._decode(tag_key)
                if needle in tag.casefold():
                    result.append(tag)
            return result

    def migrate_legacy(self, directory, template_path, known_tags):
        """Import unambiguous legacy Markdown files without deleting originals."""
        try:
            entries = list(os.scandir(directory))
        except FileNotFoundError:
            entries = []

        candidates_by_filename = {}
        for tag in set(known_tags):
            filename = tag.replace("/", "_") + ".md"
            candidates_by_filename.setdefault(filename, []).append(tag)

        imported = []
        ambiguous = []
        with self.env.begin(write=True) as txn:
            for entry in entries:
                if not entry.is_file(follow_symlinks=True):
                    continue
                migration_key = _MIGRATION_FILE_PREFIX + self._encode(
                    entry.name
                )
                if txn.get(migration_key) is not None:
                    continue
                candidates = candidates_by_filename.get(entry.name, [])
                if len(candidates) != 1:
                    ambiguous.append(entry.path)
                    continue
                tag = candidates[0]
                tag_key = self._encode(tag)
                if txn.get(tag_key, db=self.tags_db) is not None:
                    txn.put(migration_key, b"1")
                    continue
                try:
                    with open(entry.path, "r", encoding="utf-8") as file_obj:
                        markdown = file_obj.read()
                except (OSError, UnicodeDecodeError):
                    logger.exception(
                        "Could not import legacy tag information from %s",
                        entry.path,
                    )
                    continue
                info_key = self._encode(str(uuid.uuid4()))
                txn.put(info_key, self._encode(markdown),
                        db=self.information_db)
                txn.put(tag_key, info_key, db=self.tags_db)
                txn.put(migration_key, b"1")
                imported.append(tag)

            if (
                txn.get(_MIGRATION_TEMPLATE_MARKER) is None
                and os.path.isfile(template_path)
            ):
                template_name = os.path.splitext(
                    os.path.basename(template_path)
                )[0]
                template_key = self._encode(template_name)
                try:
                    with open(template_path, "r", encoding="utf-8") as file_obj:
                        content = self._encode(file_obj.read())
                    if txn.get(template_key, db=self.templates_db) is None:
                        txn.put(
                            template_key,
                            content,
                            db=self.templates_db,
                        )
                    txn.put(_MIGRATION_TEMPLATE_MARKER, b"1")
                except (OSError, UnicodeDecodeError):
                    logger.exception(
                        "Could not import legacy tag template from %s",
                        template_path,
                    )

        if ambiguous:
            logger.warning(
                "Legacy tag information files could not be migrated "
                "unambiguously and were preserved: %s",
                ", ".join(sorted(ambiguous)),
            )
        return imported, ambiguous


def get_tag_information_store(path=None):
    """Return one shared LMDB environment per resolved path."""
    resolved_path = os.path.abspath(path or TAG_INFO_DB_PATH)
    store = _STORES.get(resolved_path)
    if store is None:
        store = TagInformationStore(resolved_path)
        _STORES[resolved_path] = store
    return store
