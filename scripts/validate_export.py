#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sanity-check a Gboard dictionary file produced by gboard_export.py.

The release workflow (.github/workflows/release.yml) runs this script on every
build, so a broken dictionary is never published. It can also be used locally
after running the exporter.

Usage:
    python scripts/validate_export.py dist/vajeban_gboard_v0.2.0.txt
    python scripts/validate_export.py gboard_fa_IR.txt --min-records 1000

Expected file format (the one gboard_export.py writes):

    # Gboard Dictionary version:2
    # Gboard Dictionary format:shortcut<TAB>word<TAB>language_tag<TAB>pos_tag
    <shortcut><TAB><word><TAB>fa-IR<TAB><POS tag, may be empty>
    ...

What is checked:
    - the file is UTF-8 without a byte order mark (BOM), uses "\\n" line
      endings and ends with a newline;
    - the two header lines are present and identical to gboard_export.HEADER;
    - there are at least --min-records records (default: 1);
    - every record has exactly four tab-separated fields;
    - the shortcut and the replacement word are not empty;
    - the shortcut contains no whitespace (Persian half-spaces, U+200C, are
      fine: they are not whitespace);
    - the language tag is fa-IR;
    - no record appears twice.

Exit status:
    0  the file is valid
    1  the file is invalid or could not be read (problems are printed to stderr)

Only the Python standard library and gboard_export.py (in the same folder) are
needed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Imported from the exporter so the header is defined in a single place.
# This works when the script is run as `python scripts/validate_export.py`,
# because Python puts the script's own folder on the import path.
from gboard_export import HEADER

# Language tag that gboard_export.py writes in the third column.
LANGUAGE_TAG = "fa-IR"

# Number of tab-separated columns per record: shortcut, word, language tag and
# POS tag. The POS tag is allowed to be empty, but the column must be present.
FIELD_COUNT = 4

# Maximum number of problems printed. A badly broken file could otherwise
# produce thousands of lines of output.
MAX_REPORTED = 10


def validate(text: str, min_records: int) -> tuple[int, list[str]]:
    """
    Check the contents of an exported dictionary.

    Args:
        text: The whole file, already decoded from UTF-8.
        min_records: The smallest acceptable number of records (header lines
            are not counted).

    Returns:
        A tuple ``(record_count, errors)``. ``errors`` is empty when the file is
        valid. Line numbers in the messages are 1-based and count the header
        lines, so they match what a text editor shows.
    """
    errors: list[str] = []

    # --- File-level checks ----------------------------------------------

    # A BOM at the start would be read as part of the first header line.
    if text.startswith("﻿"):
        errors.append("file starts with a UTF-8 BOM")
    # The exporter writes "\n" only; "\r" means the file was converted to
    # Windows line endings, which would end up inside the last field.
    if "\r" in text:
        errors.append("file contains carriage returns (CRLF line endings)")
    if not text.endswith("\n"):
        errors.append("file does not end with a newline")

    # Split on "\n" only (not str.splitlines), because splitlines also breaks on
    # other Unicode separators that could legitimately appear in text. The
    # trailing newline produces one empty last element, which is dropped.
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    # --- Header and record count ----------------------------------------

    if lines[: len(HEADER)] != HEADER:
        errors.append("the two Gboard header lines are missing or different")

    records = lines[len(HEADER):]
    if len(records) < min_records:
        errors.append(
            f"found {len(records)} record(s), expected at least {min_records}"
        )

    # --- Record checks --------------------------------------------------

    seen: set[str] = set()
    for number, line in enumerate(records, start=len(HEADER) + 1):
        fields = line.rstrip("\r").split("\t")
        if len(fields) != FIELD_COUNT:
            # The remaining checks need the four fields, so skip this line.
            errors.append(
                f"line {number}: expected {FIELD_COUNT} tab-separated fields, "
                f"found {len(fields)}"
            )
            continue

        shortcut, word, tag, _pos = fields

        if not shortcut.strip():
            errors.append(f"line {number}: empty shortcut")
        elif re.search(r"\s", shortcut):
            # Gboard shortcuts must not contain whitespace. The exporter
            # replaces spaces with half-spaces (U+200C), which `\s` does not
            # match, so valid multi-word shortcuts pass this check.
            errors.append(f"line {number}: shortcut contains whitespace")

        if not word.strip():
            errors.append(f"line {number}: empty replacement word")

        if tag != LANGUAGE_TAG:
            errors.append(
                f"line {number}: language tag is {tag!r}, expected {LANGUAGE_TAG!r}"
            )

        # Compare whole lines: the same shortcut with a different replacement
        # is a legitimate record (an extra suggestion), an identical line is not.
        if line in seen:
            errors.append(f"line {number}: duplicate record")
        seen.add(line)

    return len(records), errors


def main() -> int:
    """Parse the command line, validate the file and report the result."""
    parser = argparse.ArgumentParser(
        description="Validate a Gboard dictionary file produced by gboard_export.py."
    )
    parser.add_argument("dictionary", type=Path, help="Path to the exported .txt file")
    parser.add_argument(
        "--min-records",
        type=int,
        default=1,
        help="Fail if the file has fewer records than this (default: 1)",
    )
    args = parser.parse_args()

    # Decode strictly: a file that is not valid UTF-8 should fail the check
    # instead of being silently repaired.
    try:
        text = args.dictionary.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: cannot read {args.dictionary}: {exc}", file=sys.stderr)
        return 1

    count, errors = validate(text, args.min_records)
    if errors:
        print(f"Invalid dictionary file: {args.dictionary}", file=sys.stderr)
        for message in errors[:MAX_REPORTED]:
            print(f"  - {message}", file=sys.stderr)
        if len(errors) > MAX_REPORTED:
            print(f"  ... and {len(errors) - MAX_REPORTED} more", file=sys.stderr)
        return 1

    print(f"OK: {args.dictionary} has {count:,} valid records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())