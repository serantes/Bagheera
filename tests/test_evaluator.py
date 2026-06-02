import pytest
from bagheerasearch.core.search_lib.search import (
    EvaluateExpression, analyze_query_properties
)


@pytest.fixture
def eval_expr():
    return EvaluateExpression()


# === BASIC OPERATORS ===

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


# === ADDITIONAL OPERATOR TESTS ===

# Equality variants
def test_operator_eq(eval_expr):
    """Test the '=' operator (case-insensitive equal)."""
    func = eval_expr.compile("artist='Pink Floyd'")
    assert func({"artist": "Pink Floyd"}) is True
    assert func({"artist": "pink floyd"}) is True
    assert func({"artist": "Pink"}) is False


def test_operator_colon(eval_expr):
    """Test the ':' operator (contains)."""
    func = eval_expr.compile("tags:vacaciones")
    data = {"tags": ["Personal", "Vacaciones", "2024"]}
    assert func(data) is True
    data_no = {"tags": ["Trabajo", "Urgente"]}
    assert func(data_no) is False


def test_operator_not_contains(eval_expr):
    """Test the '!:' operator (does not contain).

    For list values, the operator uses any() semantics: it returns True
    if ANY item in the list does NOT contain the searched value.
    """
    func = eval_expr.compile("tags!:Trabajo")
    # All items lack "Trabajo" -> True
    assert func({"tags": ["Personal", "Vacaciones"]}) is True
    # At least one item lacks "Trabajo" -> True (Vacaciones doesn't contain it)
    assert func({"tags": ["Trabajo", "Vacaciones"]}) is True
    # All items contain "Trabajo" -> False
    assert func({"tags": ["Trabajo", "MiTrabajo"]}) is False
    # Single string value: "Trabajo" contains "Trabajo" -> False
    assert func({"tags": "Trabajo"}) is False


def test_operator_greater_than(eval_expr):
    """Test the '>' operator for numeric and string comparison."""
    func = eval_expr.compile("rating > 3")
    assert func({"rating": "5"}) is True
    assert func({"rating": "2"}) is False
    assert func({"rating": "3"}) is False


def test_operator_less_than(eval_expr):
    """Test the '<' operator for numeric comparison."""
    func = eval_expr.compile("rating < 4")
    assert func({"rating": "3"}) is True
    assert func({"rating": "5"}) is False
    assert func({"rating": "4"}) is False


def test_operator_greater_equal(eval_expr):
    """Test the '>=' operator."""
    func = eval_expr.compile("rating >= 4")
    assert func({"rating": "4"}) is True
    assert func({"rating": "5"}) is True
    assert func({"rating": "3"}) is False


def test_operator_less_equal(eval_expr):
    """Test the '<=' operator."""
    func = eval_expr.compile("rating <= 3")
    assert func({"rating": "3"}) is True
    assert func({"rating": "2"}) is True
    assert func({"rating": "4"}) is False


# === LOGICAL OPERATORS ===

def test_simple_and(eval_expr):
    func = eval_expr.compile("type=Audio AND rating=5")
    assert func({"type": "Audio", "rating": "5"}) is True
    assert func({"type": "Audio", "rating": "4"}) is False
    assert func({"type": "Video", "rating": "5"}) is False


def test_simple_or(eval_expr):
    func = eval_expr.compile("type=Audio OR type=Video")
    assert func({"type": "Audio"}) is True
    assert func({"type": "Video"}) is True
    assert func({"type": "Image"}) is False


def test_simple_not(eval_expr):
    func = eval_expr.compile("NOT type=Audio")
    assert func({"type": "Video"}) is True
    assert func({"type": "Audio"}) is False


def test_not_without_condition(eval_expr):
    """NOT alone without a condition may produce different behaviors."""
    # This tests that the grammar handles 'NOT' by itself gracefully
    # (it should fail to compile and return a falsy evaluator, or handle it)
    func = eval_expr.compile("NOT")
    # This will likely return False because the grammar can't parse it
    assert callable(func)


# === IMPLICIT AND ===

def test_implicit_and(eval_expr):
    """Test that two expressions without explicit AND are implicitly ANDed."""
    func = eval_expr.compile("type=Audio rating=5")
    assert func({"type": "Audio", "rating": "5"}) is True
    assert func({"type": "Audio", "rating": "3"}) is False


def test_implicit_and_free_text(eval_expr):
    """Test free text search (matches against 'path' field)."""
    func = eval_expr.compile("vacaciones")
    data = {"path": "/home/user/vacaciones/foto.jpg"}
    assert func(data) is True

    data_no_match = {"path": "/home/user/trabajo/foto.jpg"}
    assert func(data_no_match) is False


# === NESTED PARENTHESES ===

def test_nested_parentheses(eval_expr):
    expr = "((type=Audio OR type=Video) AND (rating >= 4))"
    func = eval_expr.compile(expr)
    assert func({"type": "Audio", "rating": "5"}) is True
    assert func({"type": "Audio", "rating": "3"}) is False
    assert func({"type": "Image", "rating": "5"}) is False


def test_complex_nested_expression(eval_expr):
    expr = "NOT (type=Image AND rating < 3)"
    func = eval_expr.compile(expr)
    assert func({"type": "Audio", "rating": "5"}) is True
    assert func({"type": "Image", "rating": "5"}) is True
    assert func({"type": "Image", "rating": "2"}) is False


# === EMPTY / INVALID INPUTS ===

def test_empty_expression(eval_expr):
    func = eval_expr.compile("")
    assert callable(func)
    assert func({"type": "Audio"}) is True  # Empty expression matches all


def test_whitespace_expression(eval_expr):
    func = eval_expr.compile("   ")
    assert callable(func)
    assert func({"type": "Audio"}) is True


def test_none_expression(eval_expr):
    func = eval_expr.compile(None)  # type: ignore
    assert callable(func)
    assert func({"type": "Audio"}) is True


def test_invalid_expression(eval_expr):
    """An invalid expression should return a callable that returns False."""
    func = eval_expr.compile("== == === ")
    assert callable(func)
    # Invalid syntax -> compilation fails -> returns lambda: False
    assert func({"any": "thing"}) is False


# === EMPTY VALUE QUERIES ===

def test_empty_value_equals(eval_expr):
    """tags=\"\" should match files with no tags."""
    func = eval_expr.compile('tags=""')
    assert func({"tags": ""}) is True
    assert func({"tags": []}) is True
    assert func({"tags": ["algo"]}) is False


def test_empty_value_not_equal(eval_expr):
    """tags!=\"\" should match files with at least one tag."""
    func = eval_expr.compile('tags!=""')
    assert func({"tags": ["algo"]}) is True
    assert func({"tags": ""}) is False
    assert func({"tags": []}) is False


def test_empty_value_contains(eval_expr):
    """tags: should match files with empty tags."""
    # property: (no value) means "check if property is empty"
    func = eval_expr.compile("tags:")
    assert func({"tags": ""}) is True
    assert func({"tags": []}) is True


def test_empty_value_not_contains(eval_expr):
    """tags!: should match files with non-empty tags."""
    func = eval_expr.compile("tags!:")
    assert func({"tags": ["algo"]}) is True
    assert func({"tags": ""}) is False
    assert func({"tags": []}) is False


# === LIST-TYPE VALUE HANDLING ===

def test_list_any_match(eval_expr):
    """When a property is a list, the condition matches if ANY item matches."""
    func = eval_expr.compile("tags=Urgente")
    data = {"tags": ["Personal", "Urgente", "2024"]}
    assert func(data) is True

    data_no = {"tags": ["Personal", "Vacaciones"]}
    assert func(data_no) is False


def test_empty_list_equals(eval_expr):
    """Empty list should be treated as empty value."""
    func = eval_expr.compile("tags=something")
    assert func({"tags": []}) is False


def test_list_with_colon(eval_expr):
    """Contains operator (:) with list values."""
    func = eval_expr.compile("tags:Personal")
    data = {"tags": ["Personal", "Vacaciones"]}
    assert func(data) is True

    data_partial = {"tags": ["Person"]}
    assert func(data_partial) is False


# === QUOTED VALUES ===

def test_quoted_string_value(eval_expr):
    func = eval_expr.compile("artist='Pink Floyd'")
    assert func({"artist": "Pink Floyd"}) is True
    assert func({"artist": "The Wall"}) is False


def test_double_quoted_string_value(eval_expr):
    func = eval_expr.compile('artist="Pink Floyd"')
    assert func({"artist": "Pink Floyd"}) is True


# === analyze_query_properties ===

def test_analyze_query_properties_dates():
    result = analyze_query_properties("modified=2024-01-01")
    assert result["dates"] == 1
    assert result["mimetype"] == 0
    assert result["property"] == 0
    assert result["xattr"] == 0


def test_analyze_query_properties_mimetype():
    result = analyze_query_properties("type=Audio")
    assert result["mimetype"] == 1

    result2 = analyze_query_properties("mimetype=image")
    assert result2["mimetype"] == 1


def test_analyze_query_properties_xattr():
    result = analyze_query_properties("rating=5")
    assert result["xattr"] == 1

    result2 = analyze_query_properties("tags=Vacaciones")
    assert result2["xattr"] == 1

    result3 = analyze_query_properties("usercomment=test")
    assert result3["xattr"] == 1


def test_analyze_query_properties_other():
    result = analyze_query_properties("width > 800")
    assert result["property"] == 1
    assert result["dates"] == 0
    assert result["mimetype"] == 0
    assert result["xattr"] == 0


def test_analyze_query_properties_mixed():
    query = "type=Audio modified=2024-01-01 rating >= 4"
    result = analyze_query_properties(query)
    assert result["mimetype"] == 1
    assert result["dates"] == 1
    assert result["xattr"] == 1


def test_analyze_query_properties_no_match():
    result = analyze_query_properties("vacaciones")
    assert result == {"dates": 0, "mimetype": 0, "property": 0, "xattr": 0}


def test_analyze_query_properties_empty():
    result = analyze_query_properties("")
    assert result == {"dates": 0, "mimetype": 0, "property": 0, "xattr": 0}


def test_analyze_query_properties_case_insensitive():
    result = analyze_query_properties("MODIFIED=2024-01-01")
    assert result["dates"] == 1


def test_analyze_query_properties_quoted_values():
    """Quoted values should not affect property detection."""
    result = analyze_query_properties("artist=\"Pink Floyd\" type=Audio")
    assert result["mimetype"] == 1
    assert result["property"] == 1