from types import SimpleNamespace

from bagheeraview.core import metadatamanager


def test_read_datetime_prefers_original_capture_time(monkeypatch):
    class Datum:
        def __init__(self, key, value):
            self._key = key
            self._value = value

        def key(self):
            return self._key

        def toString(self):
            return self._value

    class Image:
        def readMetadata(self):
            pass

        def exifData(self):
            return [
                Datum("Exif.Image.DateTime", "2020:01:02 03:04:05"),
                Datum("Exif.Photo.DateTimeOriginal", "2024:05:06 07:08:09"),
            ]

    monkeypatch.setattr(metadatamanager, "HAVE_EXIV2", True)
    monkeypatch.setattr(
        metadatamanager, "exiv2",
        SimpleNamespace(ImageFactory=SimpleNamespace(open=lambda _path: Image())))

    assert metadatamanager.MetadataManager.read_datetime("photo.jpg") == (
        "2024-05-06 07:08:09")
