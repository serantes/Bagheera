import pytest
import sys
from bagheerasearch.core.app import main


def test_version_output(capsys, monkeypatch):
    # Simulate running 'bagheerasearch --version'
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--version"])
    main()

    captured = capsys.readouterr()
    assert "Bagheera Search Tool v" in captured.out


def test_missing_year_with_month(monkeypatch):
    # Should raise a ValueError if month is provided but not year
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--month", "5"])
    with pytest.raises(ValueError, match="Missing --year"):
        main()


def test_help_query(capsys, monkeypatch):
    # Simulate running 'bagheerasearch --help-query' and check for expected output
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--help-query"])
    main()
    captured = capsys.readouterr()
    assert "Baloo offers a rich syntax" in captured.out
