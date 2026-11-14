#!/usr/bin/env python3
# flake8: noqa: E501
"""
Bagheera Search Tool - CLI Client
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple
from .help_texts import HelpTexts

# --- CONFIGURATION ---
PROG_NAME = "Bagheera Search Tool"
PROG_ID = "bagheerasearch"
PROG_VERSION = "1.1.0"
PROG_BY = "Ignacio Serantes"
PROG_DATE = "2026-11-14"

CONFIG_DIR = Path.home() / ".config" / PROG_ID
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Loads user configuration from disk."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(HelpTexts.ERR_LOAD_CONFIG.format(e))
    return {}


def save_config(config: dict) -> None:
    """Saves user configuration to disk."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except OSError as e:
        print(HelpTexts.ERR_SAVE_CONFIG.format(e))


def print_help_query() -> None:
    """Prints the detailed help for query syntax."""
    print(HelpTexts.HELP_QUERY_TEMPLATE.format(prog_name=PROG_NAME, prog_id=PROG_ID))


def print_version() -> None:
    """Prints version information."""
    print(f"{PROG_NAME} v{PROG_VERSION} - {PROG_DATE}")
    print(
        HelpTexts.COPYRIGHT_INFO.format(year=PROG_DATE[:4], author=PROG_BY)
    )


class Subquery(NamedTuple):
    operator: str
    query: str
    having: Optional[str]


def parse_query_clauses(query: str) -> Tuple[str, Optional[str], List[Subquery]]:
    """Split the query into independently evaluated search sections."""
    main_section: Dict[str, List[str]] = {"query": [], "having": []}
    current = main_section
    subquery_sections: List[Tuple[str, Dict[str, List[str]]]] = []
    section = "query"
    quote = None
    start = 0
    i = 0
    while i < len(query):
        char = query[i]
        if char == "\\" and i + 1 < len(query):
            i += 2
            continue
        if quote:
            if char == quote:
                quote = None
        elif char == '"' or (char == "'" and
                             (i == 0 or query[i - 1].isspace() or query[i - 1] in "=!:<>")):
            quote = char
        elif i == 0 or query[i - 1].isspace():
            keyword = next(
                (word for word in ("HAVING", "SUBQUERY")
                 if query.startswith(word, i)
                 and (i + len(word) == len(query) or query[i + len(word)].isspace())),
                None,
            )
            if keyword:
                text = query[start:i].strip()
                operator = "AND"
                if keyword == "SUBQUERY":
                    match = re.search(r"(?:^|\s)(AND NOT|OR EXCLUSIVE|OR NOT|AND|OR|NOT)\s*$", text)
                    if match:
                        operator = match.group(1)
                        text = text[:match.start()].strip()
                if text:
                    current[section].append(text)
                if keyword == "SUBQUERY":
                    current = {"query": [], "having": []}
                    subquery_sections.append((operator, current))
                    section = "query"
                else:
                    section = "having"
                i += len(keyword)
                start = i
                continue
        i += 1

    text = query[start:].strip()
    if text:
        current[section].append(text)

    return (
        " ".join(main_section["query"]),
        " AND ".join(main_section["having"]) or None,
        [Subquery(operator, " ".join(parts["query"]), " AND ".join(parts["having"]) or None)
         for operator, parts in subquery_sections],
    )


def parse_search_arguments(parser, argv=None):
    """Parse command options while retaining query words in their original order."""
    argv = sys.argv[1:] if argv is None else argv
    for arg in argv:
        if arg.split("=", 1)[0] in ("--having", "--subquery", "--subquery-having"):
            parser.error(HelpTexts.ERR_REMOVED_OPTION.format(arg))

    args, unknown_args = parser.parse_known_args(argv)
    unknown_options = [arg for arg in unknown_args if arg.startswith("-")]
    if unknown_options:
        parser.error(HelpTexts.ERR_UNKNOWN_OPTIONS.format(" ".join(unknown_options)))
    return args, unknown_args


def build_search_request(parser, args, unknown_args):
    """Build the query and options shared by CLI and library clients."""
    query_parts = [args.query] if args.query else []
    query_parts.extend(unknown_args)
    query_text, having, subqueries = parse_query_clauses(" ".join(query_parts))

    if args.day is not None and args.month is None:
        parser.error(HelpTexts.ERR_MISSING_MONTH)
    if args.month is not None and args.year is None:
        parser.error(HelpTexts.ERR_MISSING_YEAR)

    main_options = {}
    if not subqueries:
        if args.limit is not None:
            main_options["limit"] = args.limit
        if args.offset is not None:
            main_options["offset"] = args.offset
    if args.type:
        main_options["type"] = args.type
    if args.directory:
        main_options["directory"] = args.directory
    if args.year is not None:
        main_options["year"] = args.year
    if args.month is not None:
        main_options["month"] = args.month
    if args.day is not None:
        main_options["day"] = args.day
    if args.sort:
        main_options["sort"] = args.sort

    other_options = {
        "having": having,
        "id": getattr(args, "id", False),
        "konsole": getattr(args, "konsole", False),
        "limit": args.limit if subqueries and args.limit is not None else 99999999999,
        "offset": args.offset if subqueries and args.offset is not None else 0,
        "subquery": None,
        "subquery_indent": getattr(args, "subquery_indent", None) or "",
        "subquery_having": None,
        "sort": args.sort,
        "type": None,
        "verbose": getattr(args, "verbose", False),
    }
    if subqueries:
        other_options["subqueries"] = subqueries
    return query_text, main_options, other_options


def main() -> None:
    """Main entry point for the CLI tool."""
    parser = argparse.ArgumentParser(
        description=HelpTexts.CLI_DESC
    )
    parser.add_argument("query", nargs="?", help=HelpTexts.ARG_QUERY)
    parser.add_argument("-d", "--directory", help=HelpTexts.ARG_DIR)
    parser.add_argument("-i", "--id", action="store_true", help=HelpTexts.ARG_ID)
    parser.add_argument("-k", "--konsole", action="store_true", help=HelpTexts.ARG_KONSOLE)
    parser.add_argument("-l", "--limit", type=int, help=HelpTexts.ARG_LIMIT)
    parser.add_argument("-o", "--offset", type=int, help=HelpTexts.ARG_OFFSET)
    parser.add_argument("-n", "--subquery-indent", help=HelpTexts.ARG_SUBQUERY_INDENT)
    parser.add_argument("-s", "--sort", help=HelpTexts.ARG_SORT)
    parser.add_argument("-t", "--type", help=HelpTexts.ARG_TYPE)
    parser.add_argument("-v", "--verbose", action="store_true", help=HelpTexts.ARG_VERBOSE)

    parser.add_argument("--day", type=int, help=HelpTexts.ARG_DAY)
    parser.add_argument("--month", type=int, help=HelpTexts.ARG_MONTH)
    parser.add_argument("--year", type=int, help=HelpTexts.ARG_YEAR)

    parser.add_argument("--help-query", action="store_true", help=HelpTexts.ARG_HELP_QUERY)
    parser.add_argument("--version", action="store_true", help=HelpTexts.ARG_VERSION)

    args, unknown_args = parse_search_arguments(parser)

    if args.version:
        print_version()
        return

    if args.help_query:
        print_help_query()
        return

    query_text, main_options, other_options = build_search_request(parser, args, unknown_args)
    if not query_text and not other_options.get("subqueries") and not args.type and not args.directory:
        parser.print_help()
        return

    # Configuration and Sort restoring
    user_config = load_config()
    # if args.sort:
    #     if user_config.get("last_sort_order") != args.sort:
    #         user_config["last_sort_order"] = args.sort
    #         save_config(user_config)
    # elif "last_sort_order" in user_config:
    #     args.sort = user_config["last_sort_order"]

    if other_options["verbose"]:
        start_time = time.time()
        print(HelpTexts.MSG_QUERY.format(query_text))
        print(HelpTexts.MSG_MAIN_OPTS.format(main_options))
        print(HelpTexts.MSG_OTHER_OPTS.format(other_options))
        print("-" * 30)

    try:
        from .search_lib import BagheeraSearcher
        searcher = BagheeraSearcher()
        files_count = 0

        # Pre-cache constant flags and formatting strings for the loop
        show_id = other_options["id"]
        use_konsole = other_options["konsole"]
        id_fmt = HelpTexts.MSG_ID_INFO
        write = sys.stdout.write

        # Consume the library generator
        for item in searcher.search(query_text, main_options, other_options):
            path = item["path"]
            output = f"file:/'{path}'" if use_konsole else path
            if show_id:
                output = f"{output}{id_fmt.format(item['id'])}"

            write(f"{output}\n")
            files_count += 1

        if other_options["verbose"]:
            elapsed = time.time() - start_time
            if files_count == 0:
                print(HelpTexts.MSG_NO_RESULTS)
            else:
                print(HelpTexts.MSG_TOTAL_RESULTS.format(files_count, elapsed))

    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    except KeyboardInterrupt:
        # Capture Ctrl+C inside main for an immediate and clean exit
        print(HelpTexts.MSG_CANCELED)
        sys.exit(0)
    except BrokenPipeError:
        # Silence errors when used with 'head' or 'less' and the pipe is closed
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)
    except Exception as e:
        print(HelpTexts.ERR_EXEC_SEARCH.format(e))
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Backup in case the interruption occurs outside the main block of main
        print(HelpTexts.MSG_CANCELED)
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
    except Exception as e:
        print(HelpTexts.ERR_CRITICAL.format(e))
        sys.exit(1)
