from pathlib import Path

import pytest

from bagheeraview.core import filesystemwatcher


class FakeObserver:
    def __init__(self):
        self.scheduled = []
        self.unscheduled = 0

    def schedule(self, handler, path, recursive=True):
        self.scheduled.append((path, recursive))

    def unschedule_all(self):
        self.unscheduled += 1
        self.scheduled.clear()


@pytest.fixture
def watcher(monkeypatch):
    instance = filesystemwatcher.FileSystemWatcher()
    instance._observer = FakeObserver()
    instance._event_handler = object()
    monkeypatch.setattr(filesystemwatcher, "HAVE_WATCHDOG", True)
    return instance


def test_add_path_supports_nonrecursive_monitoring(watcher, tmp_path):
    watcher.add_path(str(tmp_path), recursive=False)

    assert watcher._observer.scheduled == [(str(tmp_path), False)]
    assert watcher._recursive_watches == {str(tmp_path): False}


def test_exact_watch_can_be_downgraded_from_recursive(watcher, tmp_path):
    watcher.add_path(str(tmp_path))

    watcher.add_path(str(tmp_path), recursive=False)

    assert watcher._observer.scheduled == [(str(tmp_path), False)]
    assert watcher._observer.unscheduled == 1


def test_nonrecursive_parent_does_not_cover_child_watch(watcher, tmp_path):
    child = tmp_path / "child"
    watcher.add_path(str(tmp_path), recursive=False)
    watcher.add_path(str(child))

    assert watcher._observer.scheduled == [
        (str(tmp_path), False),
        (str(child), True),
    ]


def test_readding_recursive_parent_consolidates_child_watch(watcher, tmp_path):
    child = tmp_path / "child"
    watcher.add_path(str(child))

    watcher.add_path(str(tmp_path), recursive=True)

    assert watcher._observer.scheduled == [(str(tmp_path), True)]
    assert watcher._recursive_watches == {str(tmp_path): True}


def test_remove_path_preserves_recursion_modes(watcher, tmp_path):
    parent = str(tmp_path)
    child = str(Path(parent) / "child")
    watcher.add_path(parent, recursive=False)
    watcher.add_path(child, recursive=True)
    watcher._observer.scheduled.clear()

    watcher.remove_path(child)

    assert watcher._observer.scheduled == [(parent, False)]
    assert watcher._recursive_watches == {parent: False}
