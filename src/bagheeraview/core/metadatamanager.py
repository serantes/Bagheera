"""
Metadata Manager Module for Bagheera.

This module provides a dedicated class for handling various metadata formats
like EXIF, IPTC, and XMP, using the exiv2 library.

Classes:
    MetadataManager: A class with static methods to read metadata from files.
"""
import os
import collections
import logging
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBus
try:
    import exiv2
    HAVE_EXIV2 = True
except ImportError:
    exiv2 = None
    HAVE_EXIV2 = False


from .utils import preserve_mtime
from .constants import RATING_XATTR_NAME, XATTR_NAME, UITexts


logger = logging.getLogger(__name__)

_app_modified_callback = None

MetadataResult = collections.namedtuple('MetadataResult', ['tags', 'rating'])
EMPTY_METADATA = MetadataResult([], 0)


def set_app_modified_callback(callback):
    global _app_modified_callback
    _app_modified_callback = callback


def mark_app_modified(path):
    """Triggers the application-modified callback for a path."""
    if _app_modified_callback:
        _app_modified_callback(path)


def notify_baloo(path):
    """
    Notifies the Baloo file indexer about a file change using DBus.

    This is an asynchronous, non-blocking call. It's more efficient than
    calling `balooctl` via subprocess.

    Args:
        path (str): The absolute path of the file that was modified.
    """
    if not path:
        return

    # Use QDBusMessage directly for robust calling
    msg = QDBusMessage.createMethodCall(
        "org.kde.baloo.file", "/org/kde/baloo/file",
        "org.kde.baloo.file.indexer", "indexFile"
    )
    msg.setArguments([path])
    QDBusConnection.sessionBus().call(msg, QDBus.NoBlock)


def load_common_metadata(path):
    """
    Loads tag and rating data for a path using extended attributes.
    """
    tags = []
    raw_tags = XattrManager.get_attribute(path, XATTR_NAME)
    if raw_tags:
        tags = sorted(list(set(t.strip()
                               for t in raw_tags.split(',') if t.strip())))

    raw_rating = XattrManager.get_attribute(path, RATING_XATTR_NAME, "0")
    try:
        rating = int(raw_rating)
    except (ValueError, TypeError):
        rating = 0
    return MetadataResult(tags, rating)


class MetadataManager:
    """Manages reading EXIF, IPTC, and XMP metadata."""

    @staticmethod
    def read_all_metadata(path):
        """
        Reads all available EXIF, IPTC, and XMP metadata from a file.

        Args:
            path (str): The path to the image file.

        Returns:
            dict: A dictionary containing all found metadata key-value pairs.
                  Returns an empty dictionary if exiv2 is not available or on error.
        """
        if not HAVE_EXIV2:
            return {}

        all_metadata = {}
        try:
            image = exiv2.ImageFactory.open(path)
            image.readMetadata()

            # EXIF
            for datum in image.exifData():
                if datum.toString():
                    all_metadata[datum.key()] = datum.toString()

            # IPTC
            for datum in image.iptcData():
                if datum.toString():
                    all_metadata[datum.key()] = datum.toString()

            # XMP
            for datum in image.xmpData():
                if datum.toString():
                    all_metadata[datum.key()] = datum.toString()

        except Exception as e:
            print(f"Error reading metadata for {path}: {e}")

        return all_metadata

    @staticmethod
    def write_metadata(path, metadata_dict):
        """
        Writes EXIF, IPTC, and XMP metadata back to a file.

        Args:
            path (str): The path to the image file.
            metadata_dict (dict): A dictionary of metadata keys and values.
        """
        if not HAVE_EXIV2:
            return

        try:
            image = exiv2.ImageFactory.open(path)
            image.readMetadata()

            exif = image.exifData()
            iptc = image.iptcData()
            xmp = image.xmpData()

            # Remove keys that are no longer in the dictionary
            containers = [
                (exif, exiv2.ExifKey, "Exif."),
                (iptc, exiv2.IptcKey, "Iptc."),
                (xmp, exiv2.XmpKey, "Xmp.")
            ]

            for container, key_class, prefix in containers:
                keys_to_remove = []
                for datum in container:
                    k = datum.key()
                    # Only consider keys belonging to this specific container
                    if k.startswith(prefix) and k not in metadata_dict:
                        keys_to_remove.append(k)

                for key in keys_to_remove:
                    try:
                        x_key = key_class(key)
                        it = container.findKey(x_key)
                        if it != container.end():
                            container.erase(it)
                    except Exception as e:
                        print(f"Error removing metadata key {key}: {e}")

            # Set or update values from the dictionary
            for key, value in metadata_dict.items():
                try:
                    if key.startswith("Exif."):
                        exif[key] = str(value)
                    elif key.startswith("Iptc."):
                        iptc[key] = str(value)
                    elif key.startswith("Xmp."):
                        xmp[key] = str(value)
                except Exception as e:
                    print(f"Error setting metadata key {key}: {e}")

            image.writeMetadata()
            notify_baloo(path)
            mark_app_modified(path)
        except Exception as e:
            error_msg = str(e)
            if "kerTooLargeJpegSegment" in error_msg or "38" in error_msg:
                msg = UITexts.ERROR_JPEG_METADATA_LIMIT.format(os.path.basename(path))
                logger.error(msg)
                raise IOError(msg) from e
            logger.error(f"Error writing metadata for {path}: {e}")
            raise


class XattrManager:
    """A manager class to handle reading and writing extended attributes (xattrs)."""
    @staticmethod
    def get_attribute(path_or_fd, attr_name, default_value=""):
        """
        Gets a string value from a file's extended attribute. This is a disk read.

        Args:
            path_or_fd (str or int): The path to the file or a file descriptor.
            attr_name (str): The name of the extended attribute.
            default_value (any): The value to return if the attribute is not found.

        Returns:
            str: The attribute value or the default value.
        """
        if path_or_fd is None or path_or_fd == "":
            return default_value
        try:
            return os.getxattr(path_or_fd, attr_name).decode('utf-8')
        except (OSError, AttributeError):
            return default_value

    @staticmethod
    def set_attribute(file_path, attr_name, value):
        """
        Sets a string value for a file's extended attribute.

        If the value is None or an empty string, the attribute is removed.

        Args:
            file_path (str): The path to the file.
            attr_name (str): The name of the extended attribute.
            value (str or None): The value to set.

        Raises:
            IOError: If the attribute could not be saved.
        """
        if not file_path:
            return
        try:
            with preserve_mtime(file_path):
                mark_app_modified(file_path)
                if value:
                    os.setxattr(file_path, attr_name, str(value).encode('utf-8'))
                else:
                    try:
                        os.removexattr(file_path, attr_name)
                    except OSError:
                        pass
            notify_baloo(file_path)
        except Exception as e:
            raise IOError(f"Could not save xattr '{attr_name}' "
                          "for {file_path}: {e}") from e

    @staticmethod
    def get_all_attributes(path):
        """
        Gets all extended attributes for a file as a dictionary.

        Args:
            path (str): The path to the file.

        Returns:
            dict: A dictionary mapping attribute names to values.
        """
        attributes = {}
        if not path:
            return attributes
        try:
            keys = os.listxattr(path)
            for key in keys:
                try:
                    val = os.getxattr(path, key)
                    try:
                        val_str = val.decode('utf-8')
                    except UnicodeDecodeError:
                        val_str = str(val)
                    attributes[key] = val_str
                except (OSError, AttributeError):
                    pass
        except (OSError, AttributeError):
            pass
        return attributes
