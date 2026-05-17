import pytest
from datetime import datetime, timedelta
from bagheerasearch.core.query_parser_lib.query_parser \
    import BagheeraQueryParser


@pytest.fixture
def parser():
    return BagheeraQueryParser()


def test_modified_today(parser):
    today_str = datetime.now().strftime('%Y-%m-%d')
    assert f"modified={today_str}" in parser.parse_date("MODIFIED TODAY")


def test_modified_yesterday(parser):
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    assert f"modified={yesterday_str}" in parser.parse_date(
        "MODIFIED YESTERDAY")


def test_modified_last_n_days(parser):
    # "MODIFIED LAST 2 DAYS" should generate a range from yesterday until tomorrow
    query = parser.parse_date("MODIFIED LAST 2 DAYS")
    assert "modified>=" in query
    assert "AND modified<" in query


def test_number_conversion(parser):
    # Verify that "TWO" is converted to "2" before processing
    query = parser.parse_date("MODIFIED LAST TWO DAYS")
    # If it worked, the result will be the same as using the number 2
    assert query == parser.parse_date("MODIFIED LAST 2 DAYS")


def test_ago_expression(parser):
    # "1 YEAR AGO" should search in the complete previous year
    query = parser.parse_date("MODIFIED 1 YEAR AGO")
    last_year = datetime.now().year - 1
    assert str(last_year) in query


def test_mixed_query(parser):
    # Verify it doesn't break the rest of the search
    input_q = "vacaciones MODIFIED TODAY"
    output_q = parser.parse_date(input_q)
    assert "vacaciones" in output_q
    assert "modified=" in output_q
