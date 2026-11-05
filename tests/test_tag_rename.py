from collections import deque
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import widgets


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_rename_tag_info_files_retargets_softlinks(tmp_path):
    source = tmp_path / "animals_cat.md"
    child = tmp_path / "animals_cat_dog.md"
    link = tmp_path / "favorite-animal.md"
    source.write_text("Cat", encoding="utf-8")
    child.write_text("Dog", encoding="utf-8")
    link.symlink_to(source.name)

    renamed = widgets._rename_tag_info_files(
        "animals/cat", "animals/feline", str(tmp_path))

    assert renamed == 2
    assert not source.exists()
    assert not child.exists()
    assert (tmp_path / "animals_feline.md").read_text(
        encoding="utf-8") == "Cat"
    assert (tmp_path / "animals_feline_dog.md").read_text(
        encoding="utf-8") == "Dog"
    assert link.read_text(encoding="utf-8") == "Cat"
    assert link.resolve() == (tmp_path / "animals_feline.md").resolve()


def test_rename_tag_info_files_does_not_overwrite_existing_file(tmp_path):
    source = tmp_path / "old.md"
    destination = tmp_path / "new.md"
    source.write_text("Old", encoding="utf-8")
    destination.write_text("New", encoding="utf-8")

    with pytest.raises(FileExistsError):
        widgets._rename_tag_info_files("old", "new", str(tmp_path))

    assert source.read_text(encoding="utf-8") == "Old"
    assert destination.read_text(encoding="utf-8") == "New"


def test_update_config_for_tag_rename_updates_quick_tags_and_regions(
        monkeypatch):
    config = {
        "person_tags": "People/Alice, Pet",
        "last_region_name": "People/Alice",
    }
    monkeypatch.setattr(widgets, "APP_CONFIG", config)
    main_win = SimpleNamespace(
        mru_tags=deque(
            ["People/Alice", "People/Alice/Child", "Other"],
            maxlen=10),
        face_names_history=["People/Alice", "People/Alice/Child"])

    widgets._update_config_for_tag_rename(
        "People/Alice", "People/Anne", main_win)

    assert config["person_tags"] == "People/Anne, Pet"
    assert config["last_region_name"] == "People/Anne"
    assert list(main_win.mru_tags) == [
        "People/Anne", "People/Anne/Child", "Other"]
    assert main_win.face_names_history == [
        "People/Anne", "People/Anne/Child"]


def test_partial_tag_rename_confirms_and_updates_associated_data(
        qapp, tmp_path, monkeypatch):
    source = tmp_path / "selected.jpg"
    source.touch()
    (tmp_path / "People_Alice.md").write_text(
        "Information", encoding="utf-8")
    config = {"person_tags": "People", "mru_tags": []}
    monkeypatch.setattr(widgets, "APP_CONFIG", config)
    monkeypatch.setattr(widgets, "DIRECTORY_TAG_INFO", str(tmp_path))

    class FakeRecognitionDB:
        def __init__(self):
            self.renamed = None

        def get_all_faces(self):
            return [{"tag": "People/Alice"}]

        def rename_tag(self, old_tag, new_tag):
            self.renamed = (old_tag, new_tag)
            return 1

    recognition_db = FakeRecognitionDB()
    monkeypatch.setattr(
        "bagheeraview.core.personrecognition.PersonRecognitionDB._instance",
        recognition_db)
    confirmation_text = []
    monkeypatch.setattr(
        widgets.QMessageBox, "question",
        lambda _parent, _title, text, *_args: (
            confirmation_text.append(text) or widgets.QMessageBox.Yes))

    saved = []
    main_win = SimpleNamespace(
        proxy_model=object(),
        mru_tags=deque(["People/Alice"], maxlen=10),
        face_names_history=["People/Alice"],
        save_config=lambda: saved.append(True))
    dialog = widgets.TagRenameDialog(
        "People/Alice", main_win, all_files=False)
    dialog.found_files = [str(source)]
    dialog.edit_path.setText("People/Anne")

    updated_xattrs = []
    monkeypatch.setattr(
        widgets.XattrManager, "get_attribute",
        lambda *args: "People/Alice")
    monkeypatch.setattr(
        widgets.XattrManager, "set_attribute",
        lambda *args: updated_xattrs.append(args))
    regions = [{"type": "Face", "name": "Alice"}]
    saved_regions = []
    monkeypatch.setattr(
        widgets.XmpManager, "load_regions", lambda _path: regions)
    monkeypatch.setattr(
        widgets.XmpManager, "save_regions",
        lambda path, updated: saved_regions.append((path, updated)))

    dialog.accept_rename()

    assert len(confirmation_text) == 1
    assert "People/Alice" in confirmation_text[0]
    assert "People/Anne" in confirmation_text[0]
    assert recognition_db.renamed == ("People/Alice", "People/Anne")
    assert updated_xattrs == [(str(source), widgets.XATTR_NAME,
                               "People/Anne")]
    assert saved_regions == [(str(source), [
        {"type": "Face", "name": "Anne"}])]
    assert (tmp_path / "People_Anne.md").exists()
    assert list(main_win.mru_tags) == ["People/Anne"]
    assert main_win.face_names_history == ["People/Anne"]
    assert saved == [True]


@pytest.mark.parametrize(
    ("region_type", "history_attribute", "config_key"),
    [
        ("Face", "face_names_history", "face_names_history"),
        ("Pet", "pet_names_history", "pet_names_history"),
        ("Body", "body_names_history", "body_names_history"),
        ("Object", "object_names_history", "object_names_history"),
        ("Landmark", "landmark_names_history", "landmark_names_history"),
    ],
)
def test_face_name_mru_discards_tags_that_no_longer_exist(
        qapp, monkeypatch, region_type, history_attribute, config_key):
    config = {
        "person_tags": "Root",
        "pet_tags": "Root",
        "body_tags": "Root",
        "object_tags": "Root",
        "landmark_tags": "Root",
    }
    monkeypatch.setattr(widgets, "APP_CONFIG", config)
    saves = []
    main_win = SimpleNamespace(
        tag_edit_widget=SimpleNamespace(available_tags=["Root/Keep"]),
        save_config=lambda: saves.append(True),
    )
    setattr(main_win, history_attribute, ["Root/Keep", "Root/Deleted"])

    input_widget = widgets.FaceNameInputWidget(
        main_win, region_type=region_type)
    input_widget.load_data(["Root/Keep", "Root/Deleted"])

    assert input_widget.get_history() == ["Root/Keep"]
    assert [input_widget.name_combo.itemText(i)
            for i in range(input_widget.name_combo.count())] == ["Keep"]
    assert getattr(main_win, history_attribute) == ["Root/Keep"]
    assert config[config_key] == ["Root/Keep"]
    assert saves == [True]
