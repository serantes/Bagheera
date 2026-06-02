#!/usr/bin/env python

"""
Bagheera Query Parser
Converts natural language English date expressions into Baloo-compatible
queries.
"""

import calendar
import re
from datetime import datetime, timedelta
from typing import Dict, Optional


class BagheeraQueryParser:
    # Compile regex for number conversion once
    NUMBER_MAP: Dict[str, int] = {
        'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5,
        'SIX': 6, 'SEVEN': 7, 'EIGHT': 8, 'NINE': 9, 'TEN': 10,
        'ELEVEN': 11, 'TWELVE': 12, 'THIRTEEN': 13, 'FOURTEEN': 14,
        'FIFTEEN': 15, 'SIXTEEN': 16, 'SEVENTEEN': 17, 'EIGHTEEN': 18,
        'NINETEEN': 19, 'TWENTY': 20
    }

    # Pre-compile regex patterns for performance
    _NUM_PATTERN = re.compile(
        r'\b(' + '|'.join(NUMBER_MAP.keys()) + r')\b', re.IGNORECASE)
    _TODAY_PATTERN = re.compile(
        r'\bMODIFIED\s+TODAY\b', re.IGNORECASE)
    _YESTERDAY_PATTERN = re.compile(
        r'\bMODIFIED\s+YESTERDAY\b', re.IGNORECASE)
    _SIMPLE_PATTERN = re.compile(
        r"\bMODIFIED\s+(LAST|THIS)\s+(YEAR|MONTH|WEEK)\b", re.IGNORECASE)
    _LAST_N_PATTERN = re.compile(
        r"\bMODIFIED\s+LAST\s+(\d+)\s+(YEAR|MONTH|WEEK|DAY)S?\b", re.IGNORECASE)
    _AGO_PATTERN = re.compile(
        r"\bMODIFIED\s+(\d+)\s+(YEAR|MONTH|WEEK|DAY)S?\s+AGO\b", re.IGNORECASE)

    def __init__(self):
        # Initialize today, but it will be refreshed on each parse_date call
        self.today = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)

    def _convert_numbers(self, query: str) -> str:
        """
        Replaces written numbers (ONE to TWENTY) with their numeric string
        equivalent. Replacing is case insensitive.
        """
        def replace(match):
            key = match.group(0).upper()
            return str(self.NUMBER_MAP.get(key, key))

        return self._NUM_PATTERN.sub(replace, query)

    def _safe_replace_date(self, dt: datetime, year: Optional[int] = None,
                           month: Optional[int] = None,
                           day: Optional[int] = None) -> datetime:
        """Handles date replacement safely (e.g., Feb 29 on non-leap years)."""
        try:
            return dt.replace(
                year=year if year is not None else dt.year,
                month=month if month is not None else dt.month,
                day=day if day is not None else dt.day
            )
        except ValueError:
            # Likely Feb 29 issue, fallback to day 28
            return dt.replace(
                year=year if year is not None else dt.year,
                month=month if month is not None else dt.month,
                day=28
            )

    def _add_months(self, dt: datetime, months: int) -> datetime:
        """Robust month addition/subtraction."""
        month = dt.month - 1 + months
        year = dt.year + month // 12
        month = month % 12 + 1
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)

    def _get_start_of_unit(
            self, dt: datetime, unit: str, offset: int = 0) -> datetime:
        if unit == 'YEAR':
            target_year = dt.year - offset
            return dt.replace(year=target_year, month=1, day=1)
        if unit == 'MONTH':
            # Subtract offset months, then snap to day 1
            target_dt = self._add_months(dt, -offset)
            return target_dt.replace(day=1)
        if unit == 'WEEK':
            # Monday is 0
            return dt - timedelta(days=dt.weekday() + (offset * 7))
        if unit == 'DAY':
            return dt - timedelta(days=offset)
        return dt

    def _subtract_units(self, dt: datetime, unit: str, n: int) -> datetime:
        if unit == 'YEAR':
            return self._safe_replace_date(dt, year=dt.year - n)
        if unit == 'MONTH':
            return self._add_months(dt, -n)
        if unit == 'WEEK':
            return dt - timedelta(weeks=n)
        if unit == 'DAY':
            return dt - timedelta(days=n)

    def parse_date(self, query):
        # Quick exit: If the query doesn't contain 'MODIFIED ' (case sensitive),
        # we can skip the heavy regex processing entirely.
        if not query or "MODIFIED " not in query:
            return query

        self.today = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        q = self._convert_numbers(query)

        # 1. Replacement of TODAY / YESTERDAY
        q = self._TODAY_PATTERN.sub(
                   f"modified={self.today.strftime('%Y-%m-%d')}",
                   q)

        yest = self.today - timedelta(days=1)
        q = self._YESTERDAY_PATTERN.sub(
                   f"modified={yest.strftime('%Y-%m-%d')}",
                   q)

        # 2. Replacement of (LAST/THIS) (YEAR/MONTH/WEEK) tokens.
        # We use re.sub to locate these patterns anywhere within the query
        # string and replace them with their corresponding date range or value.
        def replace_simple(m):
            # Groups are uppercase due to regex, need normalization if
            # strictly matching
            mod, unit = m.groups()
            mod = mod.upper()
            unit = unit.upper()

            if mod == "THIS":
                start = self._get_start_of_unit(
                    self.today, unit).strftime('%Y-%m-%d')
                end = (self.today + timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                # LAST unit: Start of previous unit -> Start of current unit
                start = self._get_start_of_unit(self.today, unit,
                                                offset=1).strftime('%Y-%m-%d')
                end = (self._get_start_of_unit(self.today, unit)).strftime(
                    '%Y-%m-%d')
            return f"(modified>={start} AND modified<{end})"

        q = self._SIMPLE_PATTERN.sub(replace_simple, q)

        # 3. Replacement of LAST <N> (YEAR/MONTH/WEEK/DAY)
        def replace_last_n(m):
            n, unit = m.groups()
            unit = unit.upper()
            n_val = int(n)

            # Rolling window: Now minus N units TO Now (exclusive of tomorrow)
            if unit == 'DAY':
                start = (self.today -
                         timedelta(days=max(0, n_val - 1))).strftime(
                             '%Y-%m-%d')
            elif unit == 'WEEK':
                start = (self.today -
                         timedelta(days=max(0, (n_val * 7) - 1))).strftime(
                             '%Y-%m-%d')

            else:
                start = self._subtract_units(
                    self.today, unit, n_val).strftime('%Y-%m-%d')

            end = (self.today + timedelta(days=1)).strftime('%Y-%m-%d')
            return f"(modified>={start} AND modified<{end})"

        q = self._LAST_N_PATTERN.sub(replace_last_n, q)

        # 4. Replacement of <N> AGO
        def replace_ago(m):
            n, unit = m.groups()
            unit = unit.upper()
            n_val = int(n)

            # "2 MONTHS AGO": Whole calendar period of that month
            # Base is Start-Of-Current-Unit
            base_start = self._get_start_of_unit(self.today, unit, offset=0)

            # Start: Base - N
            start = self._subtract_units(base_start, unit, n_val)
            # End: Base - (N-1)
            end = self._subtract_units(base_start, unit, n_val - 1)

            return f"(modified>={start.strftime(
                '%Y-%m-%d')} AND modified<{end.strftime('%Y-%m-%d')})"

        q = self._AGO_PATTERN.sub(replace_ago, q)

        return q


if __name__ == '__main__':
    # Basic unit tests for date parsing
    test_queries = [
        "MODIFIED TODAY",
        "first MODIFIED YESTERDAY last",
        "MODIFIED ONE DAY AGO",
        "MODIFIED TWO DAYS AGO",
        "MODIFIED THREE DAYS AGO",
        "MODIFIED LAST TWO DAYS",
        "MODIFIED THIS WEEK",
        "MODIFIED LAST WEEK",
        "MODIFIED LAST TWO WEEKS",
        "MODIFIED ONE WEEK AGO",
        "MODIFIED TWO WEEKS AGO",
        "MODIFIED THREE WEEKS AGO",
        "MODIFIED THIS MONTH",
        "MODIFIED LAST MONTH",
        "MODIFIED LAST TWO MONTHS",
        "MODIFIED ONE MONTH AGO",
        "MODIFIED TWO MONTHS AGO",
        "MODIFIED THREE MONTHS AGO",
        "MODIFIED THIS YEAR",
        "MODIFIED LAST YEAR",
        "MODIFIED LAST TWO YEARS",
        "MODIFIED ONE YEAR AGO",
        "MODIFIED TWO YEARS AGO",
        "MODIFIED THREE YEARS AGO",
        "foto MODIFIED LAST 2 YEARS"
    ]

    parser = BagheeraQueryParser()
    print(f"Testing {__file__}:")
    for q in test_queries:
        print(f"  Input:  '{q}'")
        print(f"  Output: '{parser.parse_date(q)}'")
        print("-" * 20)

    test_queries = [
        "MODIFIED TODAYMODIFIED TODAY",
        "MODIFIED yesterday",
        "MODIFIED THIS MONTHMODIFIED THIS WEEK",
        "MODIFIED LAST YEARMODIFIED YESTERDAY",
        "modified TODAY",
        "modified today"
    ]
    parser = BagheeraQueryParser()
    print(f"Testing {__file__}:")
    for q in test_queries:
        print(f"  Input:  '{q}'")
        print(f"  Output: '{parser.parse_date(q)}'")
        print("-" * 20)
