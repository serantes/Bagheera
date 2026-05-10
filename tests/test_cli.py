import pytest
import sys
from bagheerasearch.core.app import main


def test_version_output(capsys, monkeypatch):
    # Simula ejecutar 'bagheerasearch --version'
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--version"])
    main()

    captured = capsys.readouterr()
    assert "Bagheera Search Tool v" in captured.out


def test_missing_year_with_month(monkeypatch):
    # Debe lanzar un ValueError si se pone mes pero no año
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--month", "5"])
    with pytest.raises(ValueError, match="Missing --year"):
        main()


def test_help_query(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bagheerasearch", "--help-query"])
    main()
    captured = capsys.readouterr()
    assert "Baloo offers a rich syntax" in captured.out
