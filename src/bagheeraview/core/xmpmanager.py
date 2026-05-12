"""
XMP Manager Module for Bagheera.

This module provides a dedicated class for handling XMP metadata, specifically
for reading and writing face region information compliant with the Metadata
Working Group (MWG) standard. It relies on the `exiv2` library for all
metadata operations.

Classes:
    XmpManager: A class with static methods to interact with XMP metadata.

Dependencies:
    - python-exiv2: The Python binding for the exiv2 library. The module will
      gracefully handle its absence by disabling its functionality.
    - utils.preserve_mtime: A utility to prevent file modification times from
      changing during metadata writes.
"""
import os
import re
import logging
from .utils import preserve_mtime
from .metadatamanager import notify_baloo, mark_app_modified
from .constants import UITexts
try:
    import exiv2
except ImportError:
    exiv2 = None

logger = logging.getLogger(__name__)


class XmpManager:
    """
    A static class that provides methods to read and write face region data
    to and from XMP metadata in image files.
    """

    @staticmethod
    def load_faces(path):
        """
        Loads face regions from a file's XMP metadata (MWG Regions).

        This method parses the XMP data structure for a `mwg-rs:RegionList`,
        extracts all regions of type 'Face', and returns them as a list of
        dictionaries.
        Each dictionary contains the face's name and its normalized coordinates
        (center x, center y, width, height).

        Args:
            path (str): The path to the image file.

        Returns:
            list: A list of dictionaries, where each dictionary represents a face.
                  Returns an empty list if exiv2 is not available or on error.
        """
        if not exiv2 or not path or not os.path.exists(path):
            return []

        faces = []
        try:
            img = exiv2.ImageFactory.open(path)
            # readMetadata() is crucial to populate the data structures.
            img.readMetadata()
            xmp = img.xmpData()

            regions = {}
            for datum in xmp:
                key = datum.key()
                if "mwg-rs:RegionList" in key:
                    # Use regex to find the index of the region in the list,
                    # e.g., RegionList[1], RegionList[2], etc.
                    m = re.search(r'RegionList\[(\d+)\]', key)
                    if m:
                        idx = int(m.group(1))
                        if idx not in regions:
                            regions[idx] = {}
                        val = datum.toString()
                        if key.endswith("/mwg-rs:Name"):
                            regions[idx]['name'] = val
                        elif key.endswith("/stArea:x"):
                            regions[idx]['x'] = float(val)
                        elif key.endswith("/stArea:y"):
                            regions[idx]['y'] = float(val)
                        elif key.endswith("/stArea:w"):
                            regions[idx]['w'] = float(val)
                        elif key.endswith("/stArea:h"):
                            regions[idx]['h'] = float(val)
                        elif key.endswith("/mwg-rs:Type"):
                            regions[idx]['type'] = val

            # Convert the structured dictionary into a flat list of faces,
            # preserving all regions (including 'Pet', etc.) to avoid data loss.
            for idx, data in sorted(regions.items()):
                if 'x' in data and 'y' in data and 'w' in data and 'h' in data:
                    faces.append(data)
        except Exception as e:
            print(f"Error loading faces from XMP: {e}")
        return faces

    @staticmethod
    def save_faces(path, faces):
        """
        Saves a list of faces to a file's XMP metadata as MWG Regions.

        This method performs a clean write by first removing all existing
        face region metadata from the file and then writing the new data.
        This method preserves the file's original modification time.

        Args:
            path (str): The path to the image file.
            faces (list): A list of face dictionaries to save.

        Returns:
            bool: True on success, False on failure.
        """
        if not exiv2 or not path:
            return False
        try:
            # Register required XMP namespaces to ensure they are recognized.
            exiv2.XmpProperties.registerNs(
                "http://www.metadataworkinggroup.com/schemas/regions/", "mwg-rs")
            exiv2.XmpProperties.registerNs(
                "http://ns.adobe.com/xmp/sType/Area#", "stArea")
            with preserve_mtime(path):
                img = exiv2.ImageFactory.open(path)
                img.readMetadata()
                xmp = img.xmpData()

                # 1) Remove all existing RegionList entries to prevent conflicts.
                keys_to_delete = [
                    d.key() for d in xmp
                    if d.key().startswith("Xmp.mwg-rs.Regions/mwg-rs:RegionList")
                ]
                for key in sorted(keys_to_delete, reverse=True):
                    try:
                        xmp_key = exiv2.XmpKey(key)
                        it = xmp.findKey(xmp_key)
                        if it != xmp.end():
                            xmp.erase(it)
                    except Exception:
                        pass

                # 2) Recreate the RegionList from the provided faces list.
                if faces:
                    # To initialize an XMP list (rdf:Bag), it is necessary to
                    # register the key as an array before it can be indexed.
                    # Failing to do so causes the "XMP Toolkit error 102:
                    # Indexing applied to non-array". A compatible way to do
                    # this with the python-exiv2 binding is to assign an
                    # XmpTextValue and specify its type as 'Bag', which
                    # correctly creates the empty array structure.
                    if exiv2 and hasattr(exiv2, 'XmpTextValue'):
                        xmp["Xmp.mwg-rs.Regions/mwg-rs:RegionList"] = \
                            exiv2.XmpTextValue("type=Bag")

                    for i, face in enumerate(faces):
                        # The index for XMP arrays is 1-based.
                        base = f"Xmp.mwg-rs.Regions/mwg-rs:RegionList[{i+1}]"
                        xmp[f"{base}/mwg-rs:Name"] = face.get('name', 'Unknown')
                        xmp[f"{base}/mwg-rs:Type"] = face.get('type', 'Face')
                        area_base = f"{base}/mwg-rs:Area"
                        xmp[f"{area_base}/stArea:x"] = str(face.get('x', 0))
                        xmp[f"{area_base}/stArea:y"] = str(face.get('y', 0))
                        xmp[f"{area_base}/stArea:w"] = str(face.get('w', 0))
                        xmp[f"{area_base}/stArea:h"] = str(face.get('h', 0))
                        xmp[f"{area_base}/stArea:unit"] = 'normalized'

                img.writeMetadata()

            notify_baloo(path)
            mark_app_modified(path)
            return True
        except Exception as e:
            error_msg = str(e)
            if "kerTooLargeJpegSegment" in error_msg or "38" in error_msg:
                msg = UITexts.ERROR_JPEG_METADATA_LIMIT.format(os.path.basename(path))
                logger.error(msg)
                raise IOError(msg) from e
            logger.error(f"Error saving faces to XMP: {e}")
            raise
