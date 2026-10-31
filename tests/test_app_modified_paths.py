import os
from types import SimpleNamespace

from bagheeraview.core import app as app_module
from bagheeraview.core.app import MainWindow
from bagheeraview.core import metadatamanager


class FakeSignal:
    def connect(self, callback):
        self.callback = callback


class FakeTimer:
    instances = []

    def __init__(self, _parent):
        self.timeout = FakeSignal()
        self.start_count = 0
        self.deleted = False
        self.__class__.instances.append(self)

    def setSingleShot(self, _single_shot):
        pass

    def setInterval(self, _interval):
        pass

    def start(self):
        self.start_count += 1

    def deleteLater(self):
        self.deleted = True


def test_app_modified_directory_timeout_restarts_for_each_file(monkeypatch, tmp_path):
    FakeTimer.instances = []
    monkeypatch.setattr(app_module, "QTimer", FakeTimer)
    window = SimpleNamespace(
        _paths_being_modified_by_app=set(),
        _app_modified_path_timers={},
    )
    window._expire_app_modified_path = lambda path: (
        MainWindow._expire_app_modified_path(window, path))
    first_path = str(tmp_path / "first.jpg")
    second_path = str(tmp_path / "second.jpg")

    MainWindow._mark_path_as_app_modified(window, first_path)
    directory_timer = window._app_modified_path_timers[str(tmp_path)]
    MainWindow._mark_path_as_app_modified(window, second_path)

    assert directory_timer.start_count == 2
    assert str(tmp_path) in window._paths_being_modified_by_app

    directory_timer.timeout.callback()

    assert str(tmp_path) not in window._paths_being_modified_by_app
    assert str(tmp_path) not in window._app_modified_path_timers
    assert directory_timer.deleted


def test_directory_event_is_ignored_while_app_modification_is_pending(tmp_path):
    directory = os.path.abspath(tmp_path)
    refresh_timer = SimpleNamespace(start_count=0)
    refresh_timer.start = lambda: setattr(
        refresh_timer, "start_count", refresh_timer.start_count + 1)
    window = SimpleNamespace(
        _paths_being_modified_by_app={directory},
        _is_loading=False,
        is_cleaning=False,
        _fs_dir_refresh_timer=refresh_timer,
    )

    MainWindow.on_fs_directory_modified(window, directory)

    assert refresh_timer.start_count == 0


def test_delete_marks_path_again_after_operation_completes(monkeypatch, tmp_path):
    path = str(tmp_path / "image.jpg")
    marked_paths = []
    forgotten_paths = []
    removed_paths = []
    window = SimpleNamespace(
        _mark_path_as_app_modified=marked_paths.append,
        _forget_path=forgotten_paths.append,
    )
    monkeypatch.setattr(
        app_module.os, "remove", lambda target: removed_paths.append(target))

    MainWindow.delete_file_by_path(window, path, permanent=True)

    assert removed_paths == [path]
    assert marked_paths == [path, path]
    assert forgotten_paths == [path]


def test_xattr_write_marks_path_after_metadata_write_and_mtime_restore(
        monkeypatch, tmp_path):
    path = tmp_path / "image.jpg"
    path.touch()
    events = []
    real_utime = app_module.os.utime

    def setxattr(_path, _name, _value):
        events.append("setxattr")

    def restore_mtime(target, **kwargs):
        real_utime(target, **kwargs)
        events.append("restore_mtime")

    monkeypatch.setattr(metadatamanager.os, "setxattr", setxattr)
    monkeypatch.setattr(metadatamanager.os, "utime", restore_mtime)
    monkeypatch.setattr(
        metadatamanager, "mark_app_modified",
        lambda _path: events.append("mark_app_modified"))
    monkeypatch.setattr(
        metadatamanager, "notify_baloo",
        lambda _path: events.append("notify_baloo"))

    metadatamanager.XattrManager.set_attribute(str(path), "user.test", "value")

    assert events == [
        "setxattr", "restore_mtime", "mark_app_modified", "notify_baloo"
    ]
