import os
from types import SimpleNamespace

import pytest

from bagheeraview.core import metadatamanager
from bagheeraview.core.utils import preserve_mtime


def test_preserve_mtime_restores_nanoseconds_when_operation_raises(tmp_path):
    path = tmp_path / "image.jpg"
    path.write_bytes(b"image data")
    original_mtime_ns = 1_700_000_000_123_456_789
    os.utime(path, ns=(original_mtime_ns, original_mtime_ns))

    with pytest.raises(RuntimeError, match="write failed"):
        with preserve_mtime(path):
            os.utime(
                path,
                ns=(original_mtime_ns + 1_000_000_000,
                    original_mtime_ns + 2_000_000_000))
            raise RuntimeError("write failed")

    assert path.stat().st_mtime_ns == original_mtime_ns


def test_gps_metadata_writes_preserve_original_mtime(tmp_path, monkeypatch):
    path = tmp_path / "image.jpg"
    path.write_bytes(b"image data")
    original_mtime_ns = 1_700_000_000_123_456_789
    os.utime(path, ns=(original_mtime_ns, original_mtime_ns))

    class FakeExif(dict):
        _end = object()

        def findKey(self, key):
            return key if key in self else self._end

        def end(self):
            return self._end

        def erase(self, key):
            del self[key]

    exif = FakeExif()

    class FakeImage:
        def readMetadata(self):
            pass

        def exifData(self):
            return exif

        def writeMetadata(self):
            stat_result = path.stat()
            os.utime(
                path,
                ns=(stat_result.st_atime_ns,
                    stat_result.st_mtime_ns + 5_000_000_000))

    image = FakeImage()
    monkeypatch.setattr(
        metadatamanager, "exiv2",
        SimpleNamespace(
            ImageFactory=SimpleNamespace(open=lambda _path: image),
            ExifKey=lambda key: key))
    monkeypatch.setattr(metadatamanager, "HAVE_EXIV2", True)
    monkeypatch.setattr(metadatamanager, "notify_baloo", lambda _path: None)
    monkeypatch.setattr(
        metadatamanager, "mark_app_modified", lambda _path: None)

    metadatamanager.MetadataManager.write_gps(str(path), 38.2, 128.4)
    assert path.stat().st_mtime_ns == original_mtime_ns

    metadatamanager.MetadataManager.clear_gps(str(path))
    assert path.stat().st_mtime_ns == original_mtime_ns
