from collections import deque
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from bagheeraview.core import widgets
from bagheeraview.core.tag_information import get_tag_information_store


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_rename_tag_information_preserves_shared_data(tmp_path):
    store = get_tag_information_store(str(tmp_path / "db"))
    store.save_info("animals/cat", "Cat")
    store.associate("favorite-animal", "animals/cat")

    renamed = widgets._rename_tag_info_entries(
        "animals/cat", "animals/feline", store
    )

    assert renamed == 1
    assert store.get_info("animals/cat") is None
    assert store.get_info("animals/feline") == "Cat"
    assert store.get_info("favorite-animal") == "Cat"


def test_rename_tag_information_does_not_overwrite_existing_tag(tmp_path):
    store = get_tag_information_store(str(tmp_path / "db"))
    store.save_info("old", "Old")
    store.save_info("new", "New")

    with pytest.raises(ValueError):
        widgets._rename_tag_info_entries("old", "new", store)

    assert store.get_info("old") == "Old"
    assert store.get_info("new") == "New"


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
    db_path = tmp_path / "tag-info-db"
    monkeypatch.setattr(widgets, "TAG_INFO_DB_PATH", str(db_path))
    store = get_tag_information_store(str(db_path))
    store.save_info("People/Alice", "Information")
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
    assert store.get_info("People/Anne") == "Information"
    assert store.get_info("People/Alice") is None
    assert (tmp_path / "People_Alice.md").exists()
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
