import pytest
import sys
from types import ModuleType
from bagheerasearch.core.app import main, parse_query_clauses


@pytest.fixture
def indexed_files_are_regular(monkeypatch):
    import importlib
    import os

    search_module = importlib.import_module("bagheerasearch.core.search_lib.search")
    file_stat = os.stat(__file__)
    monkeypatch.setattr(search_module, "stat_path", lambda path: file_stat)


def test_version_output(capsys, monkeypatch):
    # Simulate running 'bagheerasearch --version'
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--version"])
    main()

    captured = capsys.readouterr()
    assert "Bagheera Search Tool v" in captured.out


def test_missing_year_with_month(capsys, monkeypatch):
    # Should raise a SystemExit if month is provided but not year
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--month", "5"])
    # with pytest.raises(ValueError, match="Missing --year"):
    with pytest.raises(SystemExit):
        main()
        captured = capsys.readouterr()
        assert "bagheerasearch: error: Missing --year (required when --month is used)" in captured.err


def test_help_query(capsys, monkeypatch):
    # Simulate running 'bagheerasearch --help-query' and check for expected output
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--help-query"])
    main()
    captured = capsys.readouterr()
    assert "Baloo offers a rich syntax" in captured.out


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("main", ("main", None, [])),
        ("main HAVING a SUBQUERY b HAVING c", ("main", "a", [("AND", "b", "c")])),
        ("main HAVING SUBQUERY HAVING", ("main", None, [("AND", "", None)])),
        ("main SUBQUERY HAVING c", ("main", None, [("AND", "", "c")])),
        ("main HAVING a HAVING b SUBQUERY c SUBQUERY d HAVING e HAVING f",
         ("main", "a AND b", [("AND", "c", None), ("AND", "d", "e AND f")])),
        ('filename="HAVING SUBQUERY" HAVING tags="SUBQUERY"',
         ('filename="HAVING SUBQUERY"', 'tags="SUBQUERY"', [])),
        ("artist=O'Brien HAVING tags='HAVING SUBQUERY'",
         ("artist=O'Brien", "tags='HAVING SUBQUERY'", [])),
        ("main having subquery", ("main having subquery", None, [])),
        ("main HAVING a HAVING SUBQUERY SUBQUERY b",
         ("main", "a", [("AND", "", None), ("AND", "b", None)])),
        ("a AND SUBQUERY b AND NOT SUBQUERY c OR SUBQUERY d OR NOT SUBQUERY e OR EXCLUSIVE SUBQUERY f",
         ("a", None, [("AND", "b", None), ("AND NOT", "c", None), ("OR", "d", None),
                      ("OR NOT", "e", None), ("OR EXCLUSIVE", "f", None)])),
        ('a HAVING tags="OR EXCLUSIVE" OR SUBQUERY b HAVING rating=5 AND NOT SUBQUERY c',
         ("a", 'tags="OR EXCLUSIVE"', [("OR", "b", "rating=5"), ("AND NOT", "c", None)])),
        ("main NOT SUBQUERY a OR SUBQUERY b",
         ("main", None, [("NOT", "a", None), ("OR", "b", None)])),
    ],
)
def test_query_clauses(text, expected):
    assert parse_query_clauses(text) == expected


@pytest.mark.parametrize(
    ("argv", "expected_query", "expected_main", "expected_other"),
    [
        (["main", "HAVING", "a", "--type", "image", "b", "SUBQUERY",
          "c", "--limit", "3", "d", "HAVING", "e", "--offset", "2", "f"],
         "main", {"type": "image"},
         {"having": "a b", "subqueries": [("AND", "c d", "e f")],
          "limit": 3, "offset": 2}),
        (["main HAVING a SUBQUERY b HAVING c"],
         "main", {},
         {"having": "a", "subqueries": [("AND", "b", "c")]}),
        (["main", "OR", "--type", "image", "SUBQUERY", "b"],
         "main", {"type": "image"},
         {"having": None, "subqueries": [("OR", "b", None)]}),
        (["SUBQUERY", "HAVING", 'tags="SUBQUERY"'],
         "", {},
         {"having": None, "subqueries": [("AND", "", 'tags="SUBQUERY"')]}),
        (["--type", "image", "main", "HAVING"],
         "main", {"type": "image"},
         {"having": None, "subquery": None, "subquery_having": None}),
    ],
)
def test_cli_passes_clauses_to_searcher(
        argv, expected_query, expected_main, expected_other, monkeypatch):
    calls = []

    class FakeSearcher:
        def search(self, query, main_options, other_options):
            calls.append((query, main_options, other_options))
            return iter(())

    fake_module = ModuleType("bagheerasearch.core.search_lib")
    fake_module.BagheeraSearcher = FakeSearcher
    monkeypatch.setitem(sys.modules, "bagheerasearch.core.search_lib", fake_module)
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", *argv])
    main()

    assert len(calls) == 1
    query, main_options, other_options = calls[0]
    assert query == expected_query
    assert main_options == expected_main
    for key, value in expected_other.items():
        assert other_options[key] == value


@pytest.mark.parametrize("option", [
    "--having", "--subquery", "--subquery-having",
    "--subquery=foo", "-e", "-q", "-x",
])
def test_removed_options_are_rejected(option, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "main", option, "value"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("main SUBQUERY", ["a", "b", "c", "d", "e"]),
        ("main SUBQUERY first", ["a", "b", "c"]),
        ("main AND SUBQUERY first", ["a", "b", "c"]),
        ("main OR SUBQUERY first", ["a", "b", "c"]),
        ("main OR EXCLUSIVE SUBQUERY first", ["a", "b", "c"]),
        ("main NOT SUBQUERY first", ["d", "e"]),
        ("main AND NOT SUBQUERY first", ["d", "e"]),
        ("main OR NOT SUBQUERY first", ["d", "e"]),
        ("main NOT SUBQUERY first OR SUBQUERY second", ["b", "c", "d", "e"]),
        ("main SUBQUERY first AND SUBQUERY second", ["b", "c"]),
        ("main SUBQUERY first AND NOT SUBQUERY second", ["a"]),
        ("main SUBQUERY first OR SUBQUERY second", ["a", "b", "c", "d"]),
        ("main SUBQUERY first OR NOT SUBQUERY second", ["a", "b", "c", "e"]),
        ("main SUBQUERY first OR EXCLUSIVE SUBQUERY second", ["a", "d"]),
        ("main SUBQUERY first OR SUBQUERY second AND SUBQUERY third", ["a", "b", "c", "d"]),
        ("main SUBQUERY first OR SUBQUERY second OR EXCLUSIVE SUBQUERY third", ["a", "b", "c", "e"]),
        ("missing OR SUBQUERY second", []),
    ],
)
def test_cli_combines_subqueries_in_selected_folders(
        expression, expected, monkeypatch, capsys, indexed_files_are_regular):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    queries = []
    records = {
        "/one": {"first": ["a", "b"], "second": ["b"], "third": [],
                 "": ["a", "b"]},
        "/two": {"first": ["c"], "second": ["c", "d"], "third": ["c", "d", "e"],
                 "": ["c", "d", "e"]},
    }

    def execute_query(self, options):
        queries.append(dict(options))
        if options["type"] == "folder":
            return [] if options["query"] == "missing" else [
                {"id": "10", "path": "/one"}, {"id": "11", "path": "/two"}]
        return [{"id": item, "path": "/" + item}
                for item in records[options["directory"]][options["query"]]]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", expression, "--type", "image"])
    main()

    assert capsys.readouterr().out.splitlines() == ["/" + item for item in expected]
    assert queries[0]["type"] == "folder"
    assert all(query["type"] == "image" for query in queries[1:])
    assert all(query["directory"] in ("/one", "/two") for query in queries[1:])
    assert all("limit" not in query and "offset" not in query for query in queries)
    if expression.startswith("missing"):
        assert len(queries) == 1


def test_combined_having_and_final_pagination(monkeypatch, capsys, indexed_files_are_regular):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    queries = []

    def execute_query(self, options):
        queries.append(dict(options))
        if options["type"] == "folder":
            return [{"id": "10", "path": "/photos/matching"},
                    {"id": "11", "path": "/photos/other"}]
        ids = {"first": ["1", "2"], "second": ["2", "3"]}[options["query"]]
        return [{"id": item, "path": "/" + item} for item in ids]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(
        BagheeraSearcher, "_get_item_info",
        lambda self, item, file_id, needs: {"rating": {1: "5", 2: "7", 3: "7", 16: "5", 17: "4"}[file_id]},
    )
    monkeypatch.setattr(
        sys, "argv",
        ["bagheerasearch", "main HAVING rating=5 SUBQUERY first HAVING rating=5 OR SUBQUERY second HAVING rating=7",
         "--directory", "/photos", "--type", "image", "--offset", "1", "--limit", "1"],
    )
    main()

    assert capsys.readouterr().out == "/2\n"
    assert [query["query"] for query in queries] == ["main", "first", "second"]
    assert queries[0]["directory"] == "/photos" and queries[0]["type"] == "folder"
    assert all(query["directory"] == "/photos/matching" and query["type"] == "image"
               for query in queries[1:])
    assert all("limit" not in query and "offset" not in query for query in queries)


def test_empty_subquery_having_deduplicates_overlapping_folders(monkeypatch, capsys, indexed_files_are_regular):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    calls = []

    def execute_query(self, options):
        calls.append(dict(options))
        if options["type"] == "folder":
            return [{"id": "10", "path": "/parent"}, {"id": "11", "path": "/parent/child"}]
        if options["directory"] == "/parent":
            return [{"id": "1", "path": "/parent/a"}, {"id": "2", "path": "/parent/child/b"}]
        return [{"id": "2", "path": "/parent/child/b"}, {"id": "3", "path": "/parent/child/c"}]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(
        BagheeraSearcher, "_get_item_info",
        lambda self, item, file_id, needs: {"rating": "5" if file_id != 1 else "2"},
    )
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "main SUBQUERY HAVING rating=5", "--type", "image"])
    main()

    assert capsys.readouterr().out.splitlines() == ["/parent/child/b", "/parent/child/c"]
    assert [call["query"] for call in calls] == ["main", "", ""]


def test_empty_subquery_without_type_searches_all_folder_contents(monkeypatch, capsys):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    calls = []

    def execute_query(self, options):
        calls.append(dict(options))
        if options.get("type") == "folder":
            return [{"id": "1", "path": "/folder"}]
        return [{"id": "2", "path": "/folder/file"}]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "main", "SUBQUERY"])
    main()

    assert capsys.readouterr().out == "/folder/file\n"
    assert calls[1]["directory"] == "/folder"
    assert calls[1]["query"] == ""
    assert "type" not in calls[1]


@pytest.mark.parametrize("expression", ["main SUBQUERY", "main NOT SUBQUERY absent"])
def test_typed_subquery_excludes_misindexed_directories(expression, tmp_path, monkeypatch, capsys):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    folder = tmp_path / "folder"
    folder.mkdir()
    image = folder / "image.png"
    image.write_bytes(b"image")
    nested = folder / "nested"
    nested.mkdir()
    link = folder / "link"
    link.symlink_to(nested, target_is_directory=True)

    def execute_query(self, options):
        if options["query"] == "main":
            return [{"id": "1", "path": str(folder)}]
        assert options["type"] == "image"
        assert options["directory"] == str(folder)
        if options["query"] == "absent":
            return []
        return [
            {"id": "2", "path": str(image)},
            {"id": "3", "path": str(nested)},
            {"id": "4", "path": str(link)},
        ]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", expression, "--type", "image"])
    main()

    assert capsys.readouterr().out.splitlines() == [str(image)]


def test_folder_type_keeps_directory_results(tmp_path, monkeypatch, capsys):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    folder = tmp_path / "folder"
    folder.mkdir()
    nested = folder / "nested"
    nested.mkdir()
    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(
        BagheeraSearcher, "_execute_query",
        lambda self, options: ([{"id": "1", "path": str(folder)}] if options["query"] == "main"
                               else [{"id": "2", "path": str(nested)}]),
    )
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "main SUBQUERY", "--type", "Folder"])
    main()

    assert capsys.readouterr().out.splitlines() == [str(nested)]


def test_combined_zero_limit_returns_no_results(monkeypatch, capsys, indexed_files_are_regular):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(
        BagheeraSearcher, "_execute_query",
        lambda self, options: [{"id": "1", "path": "/result"}],
    )
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "main OR SUBQUERY other", "--limit", "0"])
    main()

    assert capsys.readouterr().out == ""


def test_or_not_uses_unfiltered_universe_with_global_options(monkeypatch, capsys, indexed_files_are_regular):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    queries = []
    records = {"first": ["1", "2"], "second": ["2", "3"], "": ["1", "2", "3", "4"]}

    def execute_query(self, options):
        queries.append(dict(options))
        if options["type"] == "folder":
            return [{"id": "10", "path": "/photos/matching"}]
        return [{"id": item, "path": "/" + item} for item in records[options["query"]]]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    monkeypatch.setattr(
        BagheeraSearcher, "_get_item_info",
        lambda self, item, file_id, needs: {"rating": {1: "5", 2: "7", 3: "6", 4: "4"}[file_id]},
    )
    monkeypatch.setattr(
        sys, "argv",
        ["bagheerasearch", "main SUBQUERY first HAVING rating=5 OR NOT SUBQUERY second HAVING rating=7",
         "--directory", "/photos", "--type", "image", "--year", "2025"],
    )
    main()

    assert capsys.readouterr().out.splitlines() == ["/1", "/3", "/4"]
    assert [query["query"] for query in queries] == ["main", "first", "second", ""]
    assert queries[0]["directory"] == "/photos" and queries[0]["type"] == "folder"
    assert all(query["directory"] == "/photos/matching" and query["type"] == "image"
               for query in queries[1:])
    assert all(query["year"] == 2025 for query in queries)


def test_legacy_library_subquery_still_searches_inside_folders(monkeypatch):
    from bagheerasearch.core.search_lib.search import BagheeraSearcher

    queries = []

    def execute_query(self, options):
        queries.append(dict(options))
        if options["type"] == "folder":
            return [{"id": "1", "path": "/folder"}]
        return [{"id": "2", "path": "/folder/file"}]

    monkeypatch.setattr(BagheeraSearcher, "_load_baloo_wrapper", lambda self, path: None)
    monkeypatch.setattr(BagheeraSearcher, "_execute_query", execute_query)
    searcher = BagheeraSearcher()
    options = {
        "having": None, "subquery": "child", "subquery_having": None,
        "limit": 10, "offset": 0, "type": "image",
    }

    assert list(searcher.search("main", {"type": "folder"}, options)) == [
        {"id": "2", "path": "/folder/file"}
    ]
    assert queries[1]["directory"] == "/folder"
