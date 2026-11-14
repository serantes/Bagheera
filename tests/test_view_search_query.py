import logging
from types import SimpleNamespace

import pytest

from bagheeraview.core import imagescanner
from bagheeraview.core.imagescanner import ImageScanner


@pytest.mark.parametrize(
    ("text", "query", "main", "having", "subqueries"),
    [
        ("main HAVING rating=5", "main", {}, "rating=5", []),
        ("main HAVING SUBQUERY HAVING", "main", {}, None, [("AND", "", None)]),
        ("main SUBQUERY --type image", "main", {"type": "image"}, None,
         [("AND", "", None)]),
        ('main HAVING tags="HAVING SUBQUERY" OR SUBQUERY first '
         "HAVING rating=5 AND NOT SUBQUERY second OR EXCLUSIVE SUBQUERY third "
         "OR NOT SUBQUERY fourth AND SUBQUERY fifth",
         "main", {}, 'tags="HAVING SUBQUERY"',
         [("OR", "first", "rating=5"), ("AND NOT", "second", None),
          ("OR EXCLUSIVE", "third", None), ("OR NOT", "fourth", None),
          ("AND", "fifth", None)]),
        ("main --type image SUBQUERY first --limit 0 HAVING rating=5 --offset 2",
         "main", {"type": "image"}, None, [("AND", "first", "rating=5")]),
        ("--directory '/photos with spaces' main", "main",
         {"directory": "/photos with spaces"}, None, []),
        ("""main HAVING 'tags="foo bar"'""", "main", {}, 'tags="foo bar"', []),
    ],
)
def test_view_parses_search_clauses(text, query, main, having, subqueries):
    actual_query, actual_main, other = ImageScanner._parse_query(None, text)
    assert (actual_query, actual_main, other["having"]) == (query, main, having)
    assert other.get("subqueries", []) == subqueries
    if "--limit 0" in text:
        assert other["limit"] == 0
        assert other["offset"] == 2


@pytest.mark.parametrize("text", [
    "main --having rating=5", "main --subquery test", "main -r test",
    "main --limit nope", "main --month 5", "main HAVING 'unclosed",
    "main --unknown value",
])
def test_invalid_view_query_is_logged_without_starting_search(text, monkeypatch, caplog):
    scanner = SimpleNamespace(_parse_query=lambda query: ImageScanner._parse_query(None, query))
    monkeypatch.setitem(imagescanner.APP_CONFIG, "search_engine", "Bagheera")
    monkeypatch.setattr(imagescanner, "HAVE_BAGHEERASEARCH_LIB", True)
    monkeypatch.setattr(imagescanner, "BagheeraSearcher",
                        lambda: pytest.fail("search must not start"))

    with caplog.at_level(logging.ERROR):
        ImageScanner._search(scanner, text)
    assert "Arguments error:" in caplog.text


def test_view_executes_combined_search_with_having_and_pagination(tmp_path, monkeypatch):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    folder = tmp_path / "folder"
    folder.mkdir()
    paths = [folder / f"{n}.jpg" for n in (1, 2, 3)]
    for path in paths:
        path.touch()
    calls = []

    def execute_query(self, options):
        calls.append(dict(options))
        if options["type"] == "folder":
            return [{"id": "10", "path": str(folder)}]
        ids = {"first": [1, 2], "second": [2, 3]}[options["query"]]
        return [{"id": str(i), "path": str(paths[i - 1])} for i in ids]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(BagheeraSearcher, "_get_item_info",
                        lambda self, item, file_id, needs: {
                            "rating": "5", "tags": ["orange cat"]})
    monkeypatch.setitem(imagescanner.APP_CONFIG, "search_engine", "Bagheera")
    scanner = SimpleNamespace(
        _parse_query=lambda query: ImageScanner._parse_query(None, query),
        _is_running=True, _seen_files=set(), all_files=[],
        _update_viewers=lambda: None,
    )
    ImageScanner._search(
        scanner, 'main HAVING rating=5 SUBQUERY first HAVING tags="orange cat" '
        "OR EXCLUSIVE SUBQUERY second --type image --offset 1 --limit 1 "
        "--year 2025 --month 7 --day 14",
    )

    assert scanner.all_files == [str(paths[2])]
    assert [call["query"] for call in calls] == ["main", "first", "second"]
    assert calls[0]["type"] == "folder"
    assert all(call["directory"] == str(folder) and call["type"] == "image"
               for call in calls[1:])
    assert not any(key in calls[0] for key in ("year", "month", "day"))
    assert all((call["year"], call["month"], call["day"]) == (2025, 7, 14)
               for call in calls[1:])


def test_view_empty_typed_subquery_excludes_folders(tmp_path, monkeypatch):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    folder = tmp_path / "folder"
    folder.mkdir()
    nested = folder / "nested"
    nested.mkdir()
    image = folder / "image.jpg"
    image.touch()

    def execute_query(self, options):
        if options["type"] == "folder":
            return [{"id": "1", "path": str(folder)}]
        assert options["query"] == ""
        assert options["type"] == "image"
        return [{"id": "2", "path": str(image)}, {"id": "3", "path": str(nested)}]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setitem(imagescanner.APP_CONFIG, "search_engine", "Bagheera")
    scanner = SimpleNamespace(
        _parse_query=lambda query: ImageScanner._parse_query(None, query),
        _is_running=True, _seen_files=set(), all_files=[],
        _update_viewers=lambda: None,
    )
    ImageScanner._search(scanner, "main SUBQUERY --type image")
    assert scanner.all_files == [str(image)]


def test_external_baloo_keeps_original_command_parsing(tmp_path, monkeypatch):
    image = tmp_path / "image.jpg"
    image.touch()
    calls = []
    monkeypatch.setitem(imagescanner.APP_CONFIG, "search_engine", "Baloo")
    monkeypatch.setattr(imagescanner, "SEARCH_CMD", ["baloosearch", "--type", "image"])
    monkeypatch.setattr(imagescanner.subprocess, "check_output",
                        lambda command, text: calls.append(command) or str(image))
    scanner = SimpleNamespace(_is_running=True, _seen_files=set(), all_files=[],
                              _update_viewers=lambda: None)

    ImageScanner._search(scanner, 'tags="foo bar"')

    assert calls == [["baloosearch", "--type", "image", "tags=foo bar"]]
    assert scanner.all_files == [str(image)]
