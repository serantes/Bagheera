import pytest
from bagheerasearch.core.search_lib.search import EvaluateExpression


@pytest.fixture
def eval_expr():
    return EvaluateExpression()


def test_basic_equality(eval_expr):
    func = eval_expr.compile("mimetype=image/jpeg")
    assert func({"mimetype": "image/jpeg"}) is True
    assert func({"mimetype": "text/plain"}) is False


def test_not_equal(eval_expr):
    # Bagheera supports != even if Baloo doesn't do it natively
    func = eval_expr.compile("rating != 5")
    assert func({"rating": "4"}) is True
    assert func({"rating": "5"}) is False


def test_property_comparison(eval_expr):
    # Comparison of two fields: "width > height"
    func = eval_expr.compile("width > height")
    assert func({"width": 1920, "height": 1080}) is True
    assert func({"width": 800, "height": 1200}) is False


def test_logical_operators(eval_expr):
    # Combination of AND, OR and NOT
    expr = "(type=Audio OR type=Video) AND NOT artist=Unknown"
    func = eval_expr.compile(expr)

    assert func({"type": "Audio", "artist": "Pink Floyd"}) is True
    assert func({"type": "Video", "artist": "Unknown"}) is False
    assert func({"type": "Image", "artist": "Pink Floyd"}) is False


def test_tags_matching(eval_expr):
    # Simulates the behavior of searching in tag lists
    func = eval_expr.compile("tags:vacaciones")
    data = {"tags": ["Personal", "Vacaciones", "2024"]}
    assert func(data) is True

    data_no_match = {"tags": ["Trabajo", "Urgente"]}
    assert func(data_no_match) is False


def test_case_sensitivity(eval_expr):
    # '==' is strict, ':' is flexible
    func_strict = eval_expr.compile("filename == Report.pdf")
    assert func_strict({"filename": "Report.pdf"}) is True
    assert func_strict({"filename": "report.pdf"}) is False
