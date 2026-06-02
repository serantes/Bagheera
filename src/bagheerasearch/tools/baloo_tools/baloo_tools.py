#!/usr/bin/env python3

"""
Baloo Tools Library
Helper functions to interact directly with the Baloo LMDB index.
"""

import json
import lmdb
import os
import re
import sys
import unicodedata
from datetime import datetime
from typing import List, Optional, Tuple


INTERNAL_PROPERTY_MAP = {
    'content': b'',
    'filename': b'F',
    'mimetype': b'M',
    'rating': b'R',
    'tag': b'TAG-',
    'tags': b'TA',
    'usercomment': b'C'
}

MIME_TYPE_MAP = {
    b'T0': 'Empty',
    b'T1': 'Archive',
    b'T2': 'Audio',
    b'T3': 'Video',
    b'T4': 'Image',
    b'T5': 'Document',
    b'T6': 'Spreadsheet',
    b'T7': 'Presentation',
    b'T8': 'Text',
    b'T9': 'Folder',
}

PROPERTIES_ID_MAP = {
    '0': 'Empty',
    '1': 'BitRate',
    '2': 'Channels',
    '3': 'Duration',
    '4': 'Genre',
    '5': 'SampleRate',
    '6': 'TrackNumber',
    '7': 'ReleaseYear',
    '8': 'Comment',
    '9': 'Artist',
    '10': 'Album',
    '11': 'AlbumArtist',
    '12': 'Composer',
    '13': 'Lyricist',
    '14': 'Author',
    '15': 'Title',
    '16': 'Subject',
    '17': 'Generator',
    '18': 'PageCount',
    '19': 'WordCount',
    '20': 'LineCount',
    '21': 'Language',
    '22': 'Copyright',
    '23': 'Publisher',
    '24': 'CreationDate',
    '25': 'Keywords',
    '26': 'Width',
    '27': 'Height',
    '28': 'AspectRatio',
    '29': 'FrameRate',
    '30': 'Manufacturer',
    '31': 'Model',
    '32': 'ImageDateTime',
    '33': 'ImageOrientation',
    '34': 'PhotoFlash',
    '35': 'PhotoPixelXDimension',
    '36': 'PhotoPixelYDimension',
    '37': 'PhotoDateTimeOriginal',
    '38': 'PhotoFocalLength',
    '39': 'PhotoFocalLengthIn35mmFilm',
    '40': 'PhotoExposureTime',
    '41': 'PhotoFNumber',
    '42': 'PhotoApertureValue',
    '43': 'PhotoExposureBiasValue',
    '44': 'PhotoWhiteBalance',
    '45': 'PhotoMeteringMode',
    '46': 'PhotoISOSpeedRatings',
    '47': 'PhotoSaturation',
    '48': 'PhotoSharpness',
    '49': 'PhotoGpsLatitude',
    '50': 'PhotoGpsLongitude',
    '51': 'PhotoGpsAltitude',
    '52': 'TranslationUnitsTotal',
    '53': 'TranslationUnitsWithTranslation',
    '54': 'TranslationUnitsWithDraftTranslation',
    '55': 'TranslationLastAuthor',
    '56': 'TranslationLastUpDate',
    '57': 'TranslationTemplateDate',
    '58': 'OriginUrl',
    '59': 'OriginEmailSubject',
    '60': 'OriginEmailSender',
    '61': 'OriginEmailMessageId',
    '62': 'DiscNumber',
    '63': 'Location',
    '64': 'Performer',
    '65': 'Ensemble',
    '66': 'Arranger',
    '67': 'Conductor',
    '68': 'Opus',
    '69': 'Label',
    '70': 'Compilation',
    '71': 'License',
    '72': 'Rating',
    '73': 'Lyrics',
    '74': 'ReplayGainAlbumPeak',
    '75': 'ReplayGainAlbumGain',
    '76': 'ReplayGainTrackPeak',
    '77': 'ReplayGainTrackGain',
    '78': 'Description',
    '79': 'VideoCodec',
    '80': 'AudioCodec',
    '81': 'PixelFormat',
    '82': 'ColorSpace',
    '83': 'AssistiveAlternateDescription'
}


def decode_baloo_terms(raw_bytes: bytes) -> list[str]:
    """
    Decodes the Baloo buffer by blindly concatenating the left side of \x01
    to the literal full block that preceded the last \x00.
    """
    if not raw_bytes:
        return []

    chunks = raw_bytes.split(b"\x00")
    byte_results = []
    last_base = b""

    for chunk in chunks:
        if not chunk:
            continue

        # Use partition for faster parsing (avoids double search in vs split)
        prefix_part, sep, new_base = chunk.partition(b"\x01")

        if sep:
            # Compressed entry: produces two terms usually
            if prefix_part or last_base:
                byte_results.append(last_base + prefix_part)
            if new_base:
                byte_results.append(new_base)
                last_base = new_base
            else:
                last_base = b""
        else:
            # Literal entry
            byte_results.append(chunk)
            last_base = chunk

    # Batch decoding is more efficient than repeated calls inside the loop
    return [t.decode("utf-8", errors="ignore") for t in byte_results]


def get_kfile_metadata_types(mime_type: str) -> List[str]:
    """
    Translates a MIME type into KFileMetaData categories.

    This function mirrors the C++ KFileMetaData::typesForMimeType logic,
    returning a list of general categories (Audio, Video, Image, etc.)
    based on the provided MIME type string.

    Args:
        mime_type (str): The full MIME type string.

    Returns:
        List[str]: A list of detected KFileMetaData types.
    """
    types = []

    # Basic types - startsWith checks
    if mime_type.startswith("audio/"):
        types.append("Audio")
    if mime_type.startswith("video/"):
        types.append("Video")
    if mime_type.startswith("image/"):
        types.append("Image")
    if mime_type.startswith("text/"):
        types.append("Text")

    # Generic document check
    if "document" in mime_type:
        types.append("Document")

    # PowerPoint specific rules
    if "powerpoint" in mime_type:
        types.append("Presentation")
        if "Document" not in types:
            types.append("Document")

    # Excel specific rules
    if "excel" in mime_type:
        types.append("Spreadsheet")
        if "Document" not in types:
            types.append("Document")

    # Compressed tar archives: "application/x-<compression>-compressed-tar"
    if mime_type.startswith("application/x-") and \
       mime_type.endswith("-compressed-tar"):
        types.append("Archive")

    # Static Multi-Hash mapping
    # Note: In Python, we use a dictionary of lists to simulate QMultiHash
    type_mapper = {
        "text/plain": ["Document"],
        "application/msword": ["Document"],
        "application/x-scribus": ["Document"],
        "application/vnd.openxmlformats-officedocument."
        "presentationml.presentation": ["Presentation"],
        "application/vnd.openxmlformats-officedocument."
        "presentationml.slideshow": ["Presentation"],
        "application/vnd.openxmlformats-officedocument."
        "presentationml.template": ["Presentation"],
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet": ["Spreadsheet"],
        "application/vnd.oasis.opendocument.presentation": ["Presentation"],
        "application/vnd.oasis.opendocument.spreadsheet": ["Spreadsheet"],
        "application/pdf": ["Document"],
        "application/postscript": ["Document"],
        "application/x-dvi": ["Document"],
        "application/rtf": ["Document"],
        "application/epub+zip": ["Document"],
        "application/vnd.amazon.mobi8-ebook": ["Document"],
        "application/x-mobipocket-ebook": ["Document"],
        "application/vnd.comicbook-rar": ["Document"],
        "application/vnd.comicbook+zip": ["Document"],
        "application/x-cb7": ["Document"],
        "application/x-cbt": ["Document"],
        # Archive formats
        "application/gzip": ["Archive"],
        "application/x-tar": ["Archive"],
        "application/x-tarz": ["Archive"],
        "application/x-arc": ["Archive"],
        "application/x-archive": ["Archive"],
        "application/x-bzip": ["Archive"],
        "application/x-cpio": ["Archive"],
        "application/x-lha": ["Archive"],
        "application/x-lhz": ["Archive"],
        "application/x-lrzip": ["Archive"],
        "application/x-lz4": ["Archive"],
        "application/x-lzip": ["Archive"],
        "application/x-lzma": ["Archive"],
        "application/x-lzop": ["Archive"],
        "application/x-7z-compressed": ["Archive"],
        "application/x-ace": ["Archive"],
        "application/x-astrotite-afa": ["Archive"],
        "application/x-alz": ["Archive"],
        "application/vnd.android.package-archive": ["Archive"],
        "application/x-arj": ["Archive"],
        "application/vnd.ms-cab-compressed": ["Archive"],
        "application/x-cfs-compressed": ["Archive"],
        "application/x-dar": ["Archive"],
        "application/x-lzh": ["Archive"],
        "application/x-lzx": ["Archive"],
        "application/vnd.rar": ["Archive"],
        "application/x-stuffit": ["Archive"],
        "application/x-stuffitx": ["Archive"],
        "application/x-tzo": ["Archive"],
        "application/x-ustar": ["Archive"],
        "application/x-xar": ["Archive"],
        "application/x-xz": ["Archive"],
        "application/x-zoo": ["Archive"],
        "application/zip": ["Archive"],
        "application/zlib": ["Archive"],
        "application/zstd": ["Archive"],
        # WPS Office
        "application/wps-office.doc": ["Document"],
        "application/wps-office.xls": ["Document", "Spreadsheet"],
        "application/wps-office.pot": ["Document", "Presentation"],
        "application/wps-office.wps": ["Document"],
        "application/wps-office.docx": ["Document"],
        "application/wps-office.xlsx": ["Document", "Spreadsheet"],
        "application/wps-office.pptx": ["Document", "Presentation"],
        # Others
        "text/markdown": ["Document"],
        "image/vnd.djvu+multipage": ["Document"],
        "application/x-lyx": ["Document"],
    }

    # Append mapped values if exact match is found
    if mime_type in type_mapper:
        for mapped_type in type_mapper[mime_type]:
            # Avoid duplicates if already added by prefix/contains checks
            if mapped_type not in types:
                types.append(mapped_type)

    return types


def get_mime_type_baloo_name(bstr: str) -> dict:
    """
    Parses a raw string to extract and translate its type tag.

    The function looks for a pattern starting with 'T' followed by
    a digit (e.g., T4) delimited by \x00 and returns the corresponding
    value from MIME_TYPE_MAP.

    Args:
        bstr (str): The binary string containing the raw metadata from Baloo.

    Returns:
        str: The translated type name or 'Unknown' if not found.
    """
    fields = bstr.split(b'\x00')

    # Look for the field that starts with 'T' (e.g., b'T4')
    result = {'type': "Unknown", 'mimetype': []}
    for field in fields:
        if field.startswith(b'M'):
            mime_type = field.removeprefix(b'M').decode('utf-8', errors='ignore')
            result["mimetype"] += [mime_type]

        elif field.startswith(b'T'):
            result["type"] = MIME_TYPE_MAP.get(field, "Unknown")
            break

    if result["mimetype"] == []:
        result["mimetype"] = "Unknown"

    return result


def normalize_text(text):
    """
    Remove accents/diacritics for string comparison.
    """
    if not text:
        return ""
    text = unicodedata.normalize('NFD', text)
    text = "".join(c for c in text if unicodedata.category(c) != 'Mn')
    # return text.lower().strip()
    return text.strip()


class BalooTools:
    """Class to interact directly with the Baloo LMDB index."""

    def __init__(self) -> None:
        """Initializes the connection path and opens the Baloo LMDB environment."""
        self.baloo_db_path = os.path.join(
            os.path.expanduser("~"), ".local/share/baloo/index"
        )
        self._env: Optional[lmdb.Environment] = None
        self._dbs: dict = {}

    @property
    def env(self) -> lmdb.Environment:
        """Lazy-load and cache the LMDB environment (opened once)."""
        if self._env is None:
            try:
                self._env = lmdb.Environment(
                    self.baloo_db_path,
                    subdir=False,
                    readonly=True,
                    lock=False,
                    max_dbs=20
                )
            except lmdb.Error as e:
                print(f"Warning: Failed to open Baloo LMDB environment: "
                      f"{e}", file=sys.stderr)
                raise
        return self._env

    def _open_db(self, name: bytes):
        """Cache opened database handles to avoid repeated open_db calls."""
        if name not in self._dbs:
            self._dbs[name] = self.env.open_db(name)
        return self._dbs[name]

    def _read_single_value(self, db_name: bytes, file_id: int):
        """
        Generic helper to read a single value for a given file_id from a
        specific LMDB database. Returns the raw value or None.
        """
        try:
            db = self._open_db(db_name)
            file_id_bytes = int.to_bytes(
                file_id, length=8, byteorder='little', signed=False
            )
            with self.env.begin() as txn:
                cursor = txn.cursor(db)
                if cursor.set_range(file_id_bytes):
                    for key, value in cursor:
                        if key != file_id_bytes:
                            break
                        return value
        except lmdb.Error as e:
            print(f"Warning: Failed to access Baloo LMDB index: "
                  f"{e}", file=sys.stderr)
        return None

    def get_dates(self, file_id: int) -> dict:
        """
        Retrieves file dates metadata from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            A dict with all file metadata fields.
        """
        value = self._read_single_value(b'documenttimedb', file_id)
        if value is None:
            return {}
        try:
            if len(value) == 8:
                mtime = int.from_bytes(value[:4], 'little')
                ctime = int.from_bytes(value[4:], 'little')
                mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                ctime_str = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d')
                return {'created': ctime_str, 'modified': mtime_str}
        except (ValueError, OverflowError, OSError):
            pass
        return {}

    def get_docterms(self, file_id: int) -> bytes:
        """
        Retrieves raw metadata from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            A binary string with all data read from LMDB.
        """
        value = self._read_single_value(b'docterms', file_id)
        return value if value is not None else b''

    def get_info(self, file_id: int) -> dict:
        """
        Retrieves file metadata from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            A dict with all file metadata fields.
        """
        value = self._read_single_value(b'documentdatadb', file_id)
        if value is None:
            return {}
        try:
            jvalue = json.loads(value.decode())
            return {PROPERTIES_ID_MAP.get(k, k): v for k, v in jvalue.items()}
        except (json.JSONDecodeError, KeyError):
            return {}

    def get_mime_type(self, file_id: int) -> dict:
        """
        Retrieves the MIME type of a file from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            The MIME type as a dict, or 'Unknown' if not found.
        """
        try:
            return get_mime_type_baloo_name(self.get_docterms(file_id))
        except Exception:
            return {'type': "Unknown", 'mimetype': "Unknown"}

    @staticmethod
    def _expand_tags(tags: list) -> list:
        """
        Expands a list of tag strings by adding individual word parts and
        their normalized (accent-stripped) forms. Returns a sorted list.
        """
        result_set = set(tags)
        for item in tags:
            for part in re.split(r'[ /\n\t]+', item):
                if part:
                    result_set.add(part)
                    normalize_part = normalize_text(part)
                    if normalize_part:
                        result_set.add(normalize_part)
        return sorted(result_set)

    def get_rating(self, file_id: int) -> int:
        """
        Retrieves the file rating from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            An integer value. Returns 0 if not found.
        """
        # TODO: This method is currently implemented in a naive way,
        return 0

    def get_resolution(self, file_id: int, sep: str = 'x') -> Tuple[int, int]:
        """
        Retrieves the width and height of an image/video from the Baloo index.

        Args:
            file_id: The integer ID of the file.
            sep: Separator used (unused currently, kept for compatibility).

        Returns:
            A tuple of (width, height) integers. Returns (-1, -1) if not found.
        """
        file_info = self.get_info(file_id)
        try:
            return file_info.get('Width', -1), file_info.get('Height', -1)
        except (json.JSONDecodeError, KeyError):
            return -1, -1

    def _read_xattr_value(self, file_id: int):
        """Reads the raw xattr value from the shared environment."""
        return self._read_single_value(b'docxatrrterms', file_id)

    def get_tags(self, file_id: int) -> dict:
        """
        Retrieves a string with all file tags from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            A dict with a field called tags with all tags comma separated.
        """
        value = self._read_xattr_value(file_id)
        if value is None:
            return {}

        text = value.decode('utf-8', errors='replace')
        text = re.sub(r'\x00(?![T])', '', text)
        parts = re.split(r'[\x00\x01]', text)

        tags = []
        # 'TA' elements are tags normalized to lowercase and stripped of
        # accents/diacritics, while 'TAG' elements are the original tags as
        # they were added by the user. We only add original tags (TAG- prefix).
        for p in parts:
            p = p.strip()
            if p and p.startswith('TAG-'):
                tags.append(p.removeprefix('TAG-'))

        if not tags:
            return {}

        tags = self._expand_tags(tags)
        return {'tags': tags} if tags else {}

    def get_user_comment(self, file_id: int) -> str:
        """
        Retrieves the file user comment from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            An string value. Returns '' if not found.
        """
        # TODO: This method is currently implemented in a naive way,
        return ''

    def get_xattr_terms(self, file_id: int) -> dict:
        """
        Retrieves a dict with all available file xattr terms from the Baloo
        index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            A dict with all available file xattr terms from the Baloo index.
        """
        value = self._read_xattr_value(file_id)
        if value is None:
            return {}

        tags = []
        rating = 0
        user_comment = []

        fields = value.split(b'\x00')
        for field in fields:
            if not field:
                continue

            if field.startswith(INTERNAL_PROPERTY_MAP['tag']):
                tag = field.removeprefix(INTERNAL_PROPERTY_MAP['tag'])
                tags.append(tag.decode("utf-8", errors="ignore"))
            elif field.startswith(INTERNAL_PROPERTY_MAP['usercomment']):
                comment = field.removeprefix(
                    INTERNAL_PROPERTY_MAP['usercomment'])
                user_comment.append(
                    comment.decode("utf-8", errors="ignore"))
            elif field.startswith(INTERNAL_PROPERTY_MAP['rating']):
                rating_str = field.removeprefix(
                    INTERNAL_PROPERTY_MAP['rating'])
                try:
                    rating = int(
                        rating_str.decode("utf-8", errors="ignore"))
                except ValueError:
                    rating = 0

        result = {}
        if tags:
            result['tags'] = self._expand_tags(tags)
        if rating >= 0:
            result['rating'] = rating
        if user_comment:
            result['userComment'] = user_comment

        return result


if __name__ == '__main__':
    # CLI execution support for testing
    if len(sys.argv) > 1:
        try:
            target_id = int(sys.argv[1], 16)
            bt = BalooTools()
            print('--- XATRR TERMS ---')
            print(bt.get_xattr_terms(target_id))
            print('--- TAGS ---')
            print(bt.get_tags(target_id))
        except ValueError:
            print("Error: Please provide a valid hexadecimal file ID.",
                  file=sys.stderr)
            sys.exit(1)
