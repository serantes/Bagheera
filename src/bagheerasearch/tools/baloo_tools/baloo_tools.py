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
from typing import Tuple

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
        """Initializes the connection path to the Baloo index."""
        self.baloo_db_path = os.path.join(
            os.path.expanduser("~"), ".local/share/baloo/index"
        )

    def get_info(self, file_id: int) -> json:
        """
        Retrieves file metadata from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            A json with all file metadata fields.
        """
        try:
            # Using context manager ensures the environment is closed properly
            with lmdb.Environment(
                self.baloo_db_path,
                subdir=False,
                readonly=True,
                lock=False,
                max_dbs=20
            ) as env:
                document_data_db = env.open_db(b'documentdatadb')

                with env.begin() as txn:
                    cursor = txn.cursor(document_data_db)

                    # Convert ID to 8-byte little-endian format
                    file_id_bytes = int.to_bytes(
                        file_id, length=8, byteorder='little', signed=False
                    )

                    if cursor.set_range(file_id_bytes):
                        for key, value in cursor:
                            if key != file_id_bytes:
                                break

                            try:
                                jvalue = json.loads(value.decode())
                                return {PROPERTIES_ID_MAP.get(k, k):
                                        v for k, v in jvalue.items()}
                            except (json.JSONDecodeError, KeyError):
                                return {}

        except lmdb.Error as e:
            print(f"Warning: Failed to access Baloo LMDB index: "
                  f"{e}", file=sys.stderr)

        return {}

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
            return file_info.get('26', -1), file_info.get('27', -1)
        except (json.JSONDecodeError, KeyError):
            return -1, -1

    def get_tags(self, file_id: int) -> json:
        """
        Retrieves a string with all file tags from the Baloo index.

        Args:
            file_id: The integer ID of the file.

        Returns:
            A json with a field called tags with all tags comma separated.
        """
        try:
            # Using context manager ensures the environment is closed properly
            with lmdb.Environment(
                self.baloo_db_path,
                subdir=False,
                readonly=True,
                lock=False,
                max_dbs=20
            ) as env:
                document_data_db = env.open_db(b'docxatrrterms')

                with env.begin() as txn:
                    cursor = txn.cursor(document_data_db)

                    # Convert ID to 8-byte little-endian format
                    file_id_bytes = int.to_bytes(
                        file_id, length=8, byteorder='little', signed=False
                    )

                    if cursor.set_range(file_id_bytes):
                        for key, value in cursor:
                            if key != file_id_bytes:
                                break

                            text = value.decode('utf-8', errors='replace')
                            text = re.sub(r'\x00(?![T])', '', text)
                            parts = re.split(r'[\x00\x01]', text)

                            tags = []
                            """ 'TA' elements are tags normalized to lowercase
                            and stripped of accents/diacritics, while 'TAG'
                            elements are the original tags as they were added
                            by the user. We need to process both to ensure we
                            can match tags in a case-insensitive and
                            accent-insensitive way. But we only want to add the
                            original tags to the final result, not the
                            normalized  ones, because the normalized ones are
                            not handle correctly tags with spaces and words
                            with less than three characters.
                            """
                            for p in parts:
                                p = p.strip()
                                if p:
                                    if p.startswith('TAG-'):
                                        tag = p.removeprefix('TAG-')
                                        tags.append(tag)

                            result_set = set(tags)

                            """ Must add individual parts of the tags to the
                            result set to be able to match them with queries
                            like 'tags:callas' or 'tags:maria' for tags "María
                            Callas" or "Person/María Callas". To maintain Baloo
                            tag behaviour with spaces, it's not possible to
                            search for tags="María Callas" and must search for
                            tags=María tags:Callas; items with spaces are not
                            added to avoid syntax confusion."""
                            for item in tags:
                                parts = re.split(r'[ /\n\t]+', item)

                                for part in parts:
                                    if part:
                                        result_set.add(part)
                                        normalize_part = normalize_text(part)
                                        if normalize_part:
                                            result_set.add(normalize_part)

                            tags = sorted(list(result_set))

                            if not tags:
                                return {}
                            else:
                                return {'tags': tags}

        except lmdb.Error as e:
            print(f"Warning: Failed to access Baloo LMDB index: "
                  f"{e}", file=sys.stderr)

        return {}


if __name__ == '__main__':
    # CLI execution support for testing
    if len(sys.argv) > 1:
        try:
            target_id = int(sys.argv[1], 16)
            bt = BalooTools()
            print(bt.get_info(target_id))
        except ValueError:
            print("Error: Please provide a valid hexadecimal file ID.",
                  file=sys.stderr)
            sys.exit(1)
