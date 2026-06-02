import pytest
from datetime import datetime, timedelta
from bagheerasearch.core.query_parser_lib.query_parser \
    import BagheeraQueryParser


@pytest.fixture
def parser():
    return BagheeraQueryParser()


# === TODAY / YESTERDAY ===

def test_modified_today(parser):
    today_str = datetime.now().strftime('%Y-%m-%d')
    assert f"modified={today_str}" in parser.parse_date("MODIFIED TODAY")


def test_modified_yesterday(parser):
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    assert f"modified={yesterday_str}" in parser.parse_date(
        "MODIFIED YESTERDAY")


# === LAST N DAYS/WEEKS/MONTHS/YEARS ===

def test_modified_last_n_days(parser):
    # "MODIFIED LAST 2 DAYS" should generate a range from yesterday until tomorrow
    query = parser.parse_date("MODIFIED LAST 2 DAYS")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_modified_last_n_weeks(parser):
    query = parser.parse_date("MODIFIED LAST 3 WEEKS")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_modified_last_n_months(parser):
    query = parser.parse_date("MODIFIED LAST 6 MONTHS")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_modified_last_n_years(parser):
    query = parser.parse_date("MODIFIED LAST 5 YEARS")
    assert "modified>=" in query
    assert "AND modified<" in query


# === THIS WEEK/MONTH/YEAR ===

def test_modified_this_week(parser):
    query = parser.parse_date("MODIFIED THIS WEEK")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_modified_this_month(parser):
    query = parser.parse_date("MODIFIED THIS MONTH")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_modified_this_year(parser):
    query = parser.parse_date("MODIFIED THIS YEAR")
    start_of_year = datetime.now().strftime('%Y-01-01')
    assert f"modified>={start_of_year}" in query


# === LAST WEEK/MONTH/YEAR (without number) ===

def test_modified_last_week(parser):
    query = parser.parse_date("MODIFIED LAST WEEK")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_modified_last_month(parser):
    query = parser.parse_date("MODIFIED LAST MONTH")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_modified_last_year(parser):
    query = parser.parse_date("MODIFIED LAST YEAR")
    last_year = datetime.now().year - 1
    assert str(last_year) in query


# === N DAYS/WEEKS/MONTHS/YEARS AGO ===

def test_ago_days(parser):
    query = parser.parse_date("MODIFIED 3 DAYS AGO")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_ago_weeks(parser):
    query = parser.parse_date("MODIFIED 2 WEEKS AGO")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_ago_months(parser):
    query = parser.parse_date("MODIFIED 5 MONTHS AGO")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_ago_years(parser):
    # "1 YEAR AGO" should search in the complete previous year
    query = parser.parse_date("MODIFIED 1 YEAR AGO")
    last_year = datetime.now().year - 1
    assert str(last_year) in query


# === NUMBER CONVERSION ===

def test_number_conversion(parser):
    # Verify that "TWO" is converted to "2" before processing
    query = parser.parse_date("MODIFIED LAST TWO DAYS")
    # If it worked, the result will be the same as using the number 2
    assert query == parser.parse_date("MODIFIED LAST 2 DAYS")


def test_number_conversion_mixed_case(parser):
    query = parser.parse_date("MODIFIED LAST Two DAYS")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_number_conversion_all_numbers(parser):
    # Test all number words from ONE to TWENTY
    for word, num in parser.NUMBER_MAP.items():
        query = parser.parse_date(f"MODIFIED LAST {word} DAYS")
        expected = parser.parse_date(f"MODIFIED LAST {num} DAYS")
        assert query == expected, f"Failed for {word} -> {num}"


# === MIXED QUERIES ===

def test_mixed_query(parser):
    # Verify it doesn't break the rest of the search
    input_q = "vacaciones MODIFIED TODAY"
    output_q = parser.parse_date(input_q)
    assert "vacaciones" in output_q
    assert "modified=" in output_q


def test_multiple_modified_patterns(parser):
    # Test that multiple MODIFIED patterns in the same string are processed
    query = parser.parse_date(
        "foto MODIFIED LAST WEEK report MODIFIED TODAY")
    # Both patterns should be replaced
    assert "modified>=" in query
    assert "MODIFIED" not in query or "MODIFIED" not in query.upper()


# === EDGE CASES ===

def test_empty_query(parser):
    assert parser.parse_date("") == ""


def test_none_query(parser):
    assert parser.parse_date(None) is None


def test_no_modified_keyword(parser):
    query = "foto vacaciones 2024"
    assert parser.parse_date(query) == query


def test_lowercase_modified_not_processed(parser):
    # "modified " (lowercase) should NOT be processed because the quick-exit
    # check looks for "MODIFIED " (uppercase)
    query = "modified today"
    result = parser.parse_date(query)
    assert result == query


def test_partial_modified_keyword(parser):
    # "MODIFIEDTODAY" (no space) shouldn't trigger replacement
    query = "MODIFIEDTODAY"
    result = parser.parse_date(query)
    # The quick exit checks for "MODIFIED " (with trailing space)
    assert result == query


def test_safe_replace_date_feb29_non_leap(parser):
    """Verify _safe_replace_date handles Feb 29 on non-leap years."""
    # Create a date that could cause issues (Feb 29, 2024 is a leap year)
    # but we'll try year=2025 which is not a leap year
    dt = datetime(2024, 2, 29)
    result = parser._safe_replace_date(dt, year=2025)
    assert result.day == 28
    assert result.month == 2
    assert result.year == 2025


def test_safe_replace_date_normal(parser):
    """Verify _safe_replace_date works normally for valid dates."""
    dt = datetime(2024, 3, 15)
    result = parser._safe_replace_date(dt, year=2025)
    assert result.day == 15
    assert result.month == 3
    assert result.year == 2025


def test_add_months_positive(parser):
    """Verify _add_months correctly adds months."""
    dt = datetime(2024, 1, 31)
    result = parser._add_months(dt, 1)
    assert result.year == 2024
    assert result.month == 2
    assert result.day == 29  # 2024 is a leap year


def test_add_months_negative(parser):
    """Verify _add_months correctly subtracts months."""
    dt = datetime(2024, 3, 31)
    result = parser._add_months(dt, -1)
    assert result.year == 2024
    assert result.month == 2
    assert result.day == 29


def test_add_months_cross_year(parser):
    """Verify _add_months handles year crossing."""
    dt = datetime(2024, 1, 15)
    result = parser._add_months(dt, -2)
    assert result.year == 2023
    assert result.month == 11


def test_get_start_of_unit_year(parser):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = parser._get_start_of_unit(today, 'YEAR')
    assert result.month == 1
    assert result.day == 1


def test_get_start_of_unit_month(parser):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = parser._get_start_of_unit(today, 'MONTH')
    assert result.day == 1


def test_get_start_of_unit_week(parser):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = parser._get_start_of_unit(today, 'WEEK')
    assert result.weekday() == 0  # Monday


def test_get_start_of_unit_unknown(parser):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = parser._get_start_of_unit(today, 'INVALID')
    assert result == today


def test_subtract_units_all_types(parser):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    result_year = parser._subtract_units(today, 'YEAR', 2)
    assert result_year.year == today.year - 2

    result_month = parser._subtract_units(today, 'MONTH', 3)
    expected = parser._add_months(today, -3)
    assert result_month == expected

    result_week = parser._subtract_units(today, 'WEEK', 2)
    assert result_week == today - timedelta(weeks=2)

    result_day = parser._subtract_units(today, 'DAY', 5)
    assert result_day == today - timedelta(days=5)


def test_this_day_not_processed(parser):
    """MODIFIED THIS DAY is NOT handled by the parser (only WEEK/MONTH/YEAR)."""
    query = parser.parse_date("MODIFIED THIS DAY")
    assert query == "MODIFIED THIS DAY"


def test_modified_last_one_day(parser):
    """MODIFIED LAST 1 DAY should be equivalent to MODIFIED TODAY."""
    query = parser.parse_date("MODIFIED LAST 1 DAY")
    today_str = datetime.now().strftime('%Y-%m-%d')
    assert f"modified>={today_str}" in query
    assert "AND modified<" in query