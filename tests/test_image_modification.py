import os
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageOps
from PySide6.QtWidgets import QApplication

from bagheeraview.core import app


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        app.QMessageBox, "warning",
        lambda _parent, _title, message: warnings.append(message))
    window = SimpleNamespace(
        path=None, warnings=warnings, cache=Mock(),
        _path_to_model_index={}, _mark_path_as_app_modified=Mock())
    window.get_current_selected_path = lambda: window.path
    window._can_modify_image = lambda path: app.MainWindow._can_modify_image(
        window, path)
    window._modify_image_safely = lambda path, transform, orientations: (
        app.MainWindow._modify_image_safely(window, path, transform, orientations))
    return window


def _edit(window, action):
    if action == "rotate":
        app.MainWindow.rotate_current_image(window, 90)
    elif action == "rotate_left":
        app.MainWindow.rotate_current_image(window, -90)
    else:
        app.MainWindow.flip_current_image(window, horizontal=action == "horizontal")


@pytest.mark.parametrize("action", ["rotate", "rotate_left", "horizontal", "vertical"])
@pytest.mark.parametrize(
    "kind", ["nef", "unknown", "mismatched", "animated", "hardlink", "webp", "16bit"])
def test_unsupported_image_is_left_untouched(window, tmp_path, action, kind):
    extension = {"nef": ".NEF", "unknown": ".xyz", "mismatched": ".jpg",
                 "animated": ".png", "hardlink": ".png", "webp": ".webp",
                 "16bit": ".png"}[kind]
    path = tmp_path / f"image{extension}"
    image = Image.new("RGB", (20, 10), "red")
    if kind == "animated":
        image.save(path, format="PNG", save_all=True,
                   append_images=[Image.new("RGB", (20, 10), "blue")])
    elif kind == "16bit":
        Image.new("I;16", (20, 10), 1000).save(path)
    elif kind == "webp":
        image.save(path, format="WEBP")
    elif kind == "nef":
        image.save(path, format="TIFF")
    else:
        image.save(path, format="PNG")
    if kind == "hardlink":
        os.link(path, tmp_path / "linked.png")
    original = path.read_bytes()
    original_stat = path.stat()
    window.path = str(path)

    _edit(window, action)

    assert path.read_bytes() == original
    assert path.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert len(window.warnings) == 1
    assert str(path) in window.warnings[0]
    window._mark_path_as_app_modified.assert_not_called()
    window.cache.invalidate_path.assert_not_called()
    assert list(tmp_path.glob(".bagheera-edit-*")) == []


@pytest.mark.parametrize("action", ["rotate", "horizontal", "vertical"])
def test_supported_png_is_transformed_without_losing_file_metadata(
        window, tmp_path, action):
    pytest.importorskip("exiv2")
    path = tmp_path / "image.png"
    image = Image.new("RGB", (20, 10), "red")
    image.paste("blue", (10, 0, 20, 10))
    image.save(path)
    os.chmod(path, 0o640)
    try:
        os.setxattr(path, "user.bagheera_test", b"test-tag")
    except OSError:
        pytest.skip("Filesystem does not support user extended attributes")
    before = path.stat()
    window.path = str(path)
    operations = {
        "rotate": Image.Transpose.ROTATE_270,
        "horizontal": Image.Transpose.FLIP_LEFT_RIGHT,
        "vertical": Image.Transpose.FLIP_TOP_BOTTOM,
    }

    _edit(window, action)

    assert not window.warnings
    with Image.open(path) as result:
        assert result.size == image.transpose(operations[action]).size
        assert result.convert("RGB").tobytes() == \
            image.transpose(operations[action]).tobytes()
    assert path.stat().st_mode & 0o777 == 0o640
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert os.getxattr(path, "user.bagheera_test") == b"test-tag"
    window.cache.invalidate_path.assert_called_once_with(str(path))
    assert list(tmp_path.glob(".bagheera-edit-*")) == []


@pytest.mark.parametrize("extension", ["bmp", "tiff"])
def test_other_supported_raster_formats_remain_readable(window, tmp_path, extension):
    pytest.importorskip("exiv2")
    path = tmp_path / f"image.{extension}"
    Image.new("RGB", (20, 10), "red").save(path)
    window.path = str(path)

    _edit(window, "rotate")

    assert not window.warnings
    with Image.open(path) as image:
        assert image.size == (10, 20)
        image.load()


def test_oriented_png_edit_uses_displayed_orientation(window, tmp_path):
    pytest.importorskip("exiv2")
    path = tmp_path / "image.png"
    original = Image.new("RGB", (20, 10), "red")
    original.paste("blue", (10, 0, 20, 10))
    exif = original.getexif()
    exif[274] = 6
    original.save(path, exif=exif)
    with Image.open(path) as image:
        expected = ImageOps.exif_transpose(image).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    window.path = str(path)

    _edit(window, "horizontal")

    assert not window.warnings
    with Image.open(path) as image:
        actual = ImageOps.exif_transpose(image)
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()


@pytest.mark.parametrize("action", ["rotate", "horizontal", "vertical"])
@pytest.mark.parametrize("orientation", [1, 2, 6, 8])
@pytest.mark.skipif(not shutil.which("exiftool"), reason="ExifTool is unavailable")
def test_supported_jpeg_uses_orientation_without_reencoding(
        window, tmp_path, action, orientation):
    path = tmp_path / "image.jpg"
    image = Image.new("RGB", (20, 10), "red")
    image.paste("blue", (10, 0, 20, 10))
    exif = image.getexif()
    exif[274] = orientation
    image.save(path, quality=100, exif=exif)
    with Image.open(path) as source:
        original = source.copy()
        displayed = ImageOps.exif_transpose(source)
    window.path = str(path)

    _edit(window, action)

    assert not window.warnings
    with Image.open(path) as result:
        assert result.tobytes() == original.tobytes()
        actual = ImageOps.exif_transpose(result)
        operation = {
            "rotate": Image.Transpose.ROTATE_270,
            "horizontal": Image.Transpose.FLIP_LEFT_RIGHT,
            "vertical": Image.Transpose.FLIP_TOP_BOTTOM,
        }[action]
        expected = displayed.transpose(operation)
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()


@pytest.mark.parametrize("action", ["rotate", "horizontal"])
def test_failed_encoder_leaves_original_intact(window, tmp_path, monkeypatch, action):
    pytest.importorskip("exiv2")
    path = tmp_path / "image.png"
    Image.new("RGB", (20, 10), "red").save(path)
    original = path.read_bytes()
    window.path = str(path)

    def failed_save(_image, output):
        with open(output, "wb") as file:
            file.write(b"incomplete image")
        return False

    monkeypatch.setattr(app.QImage, "save", failed_save)
    _edit(window, action)

    assert path.read_bytes() == original
    assert len(window.warnings) == 1
    window._mark_path_as_app_modified.assert_not_called()
    window.cache.invalidate_path.assert_not_called()
    assert list(tmp_path.glob(".bagheera-edit-*")) == []


def test_unverified_encoder_output_is_not_committed(window, tmp_path, monkeypatch):
    pytest.importorskip("exiv2")
    path = tmp_path / "image.png"
    Image.new("RGB", (20, 10), "red").save(path)
    original = path.read_bytes()
    window.path = str(path)
    save = app.QImage.save

    def wrong_save(image, output):
        wrong = image.copy()
        wrong.fill(0xFF0000FF)
        return save(wrong, output)

    monkeypatch.setattr(app.QImage, "save", wrong_save)
    _edit(window, "horizontal")

    assert path.read_bytes() == original
    assert len(window.warnings) == 1
    window._mark_path_as_app_modified.assert_not_called()
    assert list(tmp_path.glob(".bagheera-edit-*")) == []


def test_missing_exiv2_blocks_png_edit(window, tmp_path, monkeypatch):
    path = tmp_path / "image.png"
    Image.new("RGB", (20, 10), "red").save(path)
    original = path.read_bytes()
    window.path = str(path)
    monkeypatch.setitem(sys.modules, "exiv2", None)

    _edit(window, "rotate")

    assert path.read_bytes() == original
    assert len(window.warnings) == 1
    window._mark_path_as_app_modified.assert_not_called()


@pytest.mark.parametrize("action", ["rotate", "horizontal"])
def test_missing_exiftool_blocks_jpeg_edit(window, tmp_path, monkeypatch, action):
    path = tmp_path / "image.jpg"
    Image.new("RGB", (20, 10), "red").save(path)
    original = path.read_bytes()
    window.path = str(path)
    monkeypatch.setattr(app.shutil, "which", lambda _name: None)

    _edit(window, action)

    assert path.read_bytes() == original
    assert len(window.warnings) == 1
    window._mark_path_as_app_modified.assert_not_called()
    assert list(tmp_path.glob(".bagheera-edit-*")) == []


@pytest.mark.skipif(not shutil.which("exiftool"), reason="ExifTool is unavailable")
def test_failed_exiftool_cannot_damage_original(window, tmp_path, monkeypatch):
    path = tmp_path / "image.jpg"
    Image.new("RGB", (20, 10), "red").save(path)
    original = path.read_bytes()
    window.path = str(path)

    def failing_exiftool(command, **_kwargs):
        if "-s3" in command:
            return SimpleNamespace(stdout="1")
        with open(command[-1], "wb") as file:
            file.write(b"incomplete image")
        raise app.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(app.subprocess, "run", failing_exiftool)
    _edit(window, "rotate")

    assert path.read_bytes() == original
    assert len(window.warnings) == 1
    window._mark_path_as_app_modified.assert_not_called()
    assert list(tmp_path.glob(".bagheera-edit-*")) == []


def test_symlink_still_points_to_transformed_image(window, tmp_path):
    pytest.importorskip("exiv2")
    path = tmp_path / "image.png"
    link = tmp_path / "link.png"
    Image.new("RGB", (20, 10), "red").save(path)
    link.symlink_to(path.name)
    window.path = str(link)

    _edit(window, "rotate")

    assert not window.warnings
    assert link.is_symlink()
    with Image.open(path) as image:
        assert image.size == (10, 20)
