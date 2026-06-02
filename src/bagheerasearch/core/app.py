#!/usr/bin/env python3
# flake8: noqa: E501
"""
Bagheera Search Tool - CLI Client
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from .help_texts import HelpTexts

# --- CONFIGURATION ---
PROG_NAME = "Bagheera Search Tool"
PROG_ID = "bagheerasearch"
PROG_VERSION = "1.0.0"
PROG_BY = "Ignacio Serantes"
PROG_DATE = "2026-05-24"

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

def main() -> None:
    """Main entry point for the CLI tool."""
    parser = argparse.ArgumentParser(
        description=HelpTexts.CLI_DESC
    )
    parser.add_argument("query", nargs="?", help=HelpTexts.ARG_QUERY)
    parser.add_argument("-d", "--directory", help=HelpTexts.ARG_DIR)
    parser.add_argument("-e", "--having", help=HelpTexts.ARG_HAVING)
    parser.add_argument("-i", "--id", action="store_true", help=HelpTexts.ARG_ID)
    parser.add_argument("-k", "--konsole", action="store_true", help=HelpTexts.ARG_KONSOLE)
    parser.add_argument("-l", "--limit", type=int, help=HelpTexts.ARG_LIMIT)
    parser.add_argument("-o", "--offset", type=int, help=HelpTexts.ARG_OFFSET)
    parser.add_argument("-q", "--subquery", nargs="?", const="", default=None, help=HelpTexts.ARG_SUBQUERY)
    parser.add_argument("-n", "--subquery-indent", help=HelpTexts.ARG_SUBQUERY_INDENT)
    parser.add_argument("-x", "--subquery-having", help=HelpTexts.ARG_SUBQUERY_HAVING)
    parser.add_argument("-s", "--sort", help=HelpTexts.ARG_SORT)
    parser.add_argument("-t", "--type", help=HelpTexts.ARG_TYPE)
    parser.add_argument("-v", "--verbose", action="store_true", help=HelpTexts.ARG_VERBOSE)

    parser.add_argument("--day", type=int, help=HelpTexts.ARG_DAY)
    parser.add_argument("--month", type=int, help=HelpTexts.ARG_MONTH)
    parser.add_argument("--year", type=int, help=HelpTexts.ARG_YEAR)

    parser.add_argument("--help-query", action="store_true", help=HelpTexts.ARG_HELP_QUERY)
    parser.add_argument("--version", action="store_true", help=HelpTexts.ARG_VERSION)

    args, unknown_args = parser.parse_known_args()

    if args.version:
        print_version()
        return

    if args.help_query:
        print_help_query()
        return

    query_parts = [args.query] if args.query else []
    if unknown_args:
        query_parts.extend(unknown_args)

    query_text = " ".join(query_parts)

    if args.day is not None and args.month is None:
        parser.error(HelpTexts.ERR_MISSING_MONTH)

    if args.month is not None and args.year is None:
        parser.error(HelpTexts.ERR_MISSING_YEAR)

    if not query_text and not args.subquery and not args.type and not args.directory:
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

    # Build options dictionary
    main_options = {}
    if args.subquery is not None:
        main_options["type"] = "folder"
    else:
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
        "having": args.having,
        "id": args.id,
        "konsole": args.konsole,
        "limit": args.limit if args.limit and args.subquery is not None else 99999999999,
        "offset": args.offset if args.offset and args.subquery is not None else 0,
        "subquery": args.subquery,
        "subquery_indent": args.subquery_indent or "",
        "subquery_having": args.subquery_having,
        "sort": args.sort,
        "type": args.type if args.subquery is not None else None,
        "verbose": args.verbose,
    }

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
